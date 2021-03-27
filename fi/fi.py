import re
import srsly
from collections import OrderedDict
from itertools import chain
from io import TextIOWrapper
from pathlib import Path
from typing import Callable, Iterable, Iterator, List, Optional, Union
from spacy import util
from spacy.errors import Errors
from spacy.lang.fi import Finnish, FinnishDefaults
from spacy.language import Language
from spacy.lookups import Lookups, load_lookups
from spacy.pipeline.lemmatizer import Lemmatizer
from spacy.symbols import NOUN, VERB, ADJ, PROPN, ADV, NUM, PRON, AUX
from spacy.tokens import Doc, Span, Token
from spacy.training import Example
from spacy.vocab import Vocab
from thinc.api import Model
from voikko import libvoikko
from zipfile import ZipFile


class FinnishLemmatizer(Lemmatizer):
    compound_re = re.compile(r"\+(\w+)(?:\(\+?[\w=]+\))?")
    minen_re = re.compile(r"\b(\w+)\[Tn4\]mi")
    sti_re = re.compile(r"\b(\w+)\[Ssti\]sti")
    ny_re = re.compile(r"\[X\]\[\w+\]\[Ny\](\w+)")
    voikko_pos_to_upos = {
        "nimisana": NOUN,
        "teonsana": VERB,
        "laatusana": ADJ,
        "nimisana_laatusana": ADJ,
        "seikkasana": ADV,
        "lukusana": NUM,
        "nimi": PROPN,
        "etunimi": PROPN,
        "sukunimi": PROPN,
        "paikannimi": PROPN,
        "asemosana": PRON,
    }

    # Use singular pronoun as lemmas (similar to in universal
    # dependencies)
    pron_baseform_exceptions = {
        'me': 'minä',
        'te': 'sinä',
        'he': 'hän',
        'nämä': 'tämä',
        'nuo': 'tuo',
        'ne': 'se',
        'ken': 'kuka',
    }

    def __init__(self, vocab: Vocab, name: str = "lemmatizer", overwrite: bool = False) -> None:
        super().__init__(vocab, model=None, name=name, mode="voikko", overwrite=overwrite)
        self.voikko = libvoikko.Voikko("fi")

    def initialize(
        self,
        get_examples: Optional[Callable[[], Iterable[Example]]] = None,
        *,
        nlp: Optional[Language] = None,
        lookups: Optional[Lookups] = None,
    ):
        """Initialize the lemmatizer and load in data.
        get_examples (Callable[[], Iterable[Example]]): Function that
            returns a representative sample of gold-standard Example objects.
        nlp (Language): The current nlp object the component is part of.
        lookups (Lookups): The lookups object containing the (optional) tables
            such as "lemma_rules", "lemma_index", "lemma_exc" and
            "lemma_lookup". Defaults to None.
        """
        if lookups is None:
            lookups = load_lookups(lang=self.vocab.lang, tables=["lemma_exc"])
        self.lookups = lookups
        self._validate_tables(Errors.E1004)

    def voikko_lemmatize(self, token: Token) -> List[str]:
        """Lemmatize one token using voikko.

        token (Token): The token to lemmatize.
        RETURNS (list): The available lemmas for the string.
        """
        if token.pos in (VERB, AUX):
            univ_pos = VERB
        elif token.pos in (ADJ, ADV, NOUN, NUM, PRON, PROPN):
            univ_pos = token.pos
        else:
            return [token.orth_.lower()]

        exc_table = self.lookups.get_table("lemma_exc", {})
        pos_exc_table = exc_table.get(univ_pos, {})
        return self._lemmatize_one_word(token.orth_, pos_exc_table, univ_pos)

    def _lemmatize_one_word(self, string, exceptions, univ_pos):
        # Lemma of inflected abbreviations: BBC:n, EU:ssa
        string = string.rsplit(":", 1)[0]
        
        # Lemmatize only the last part of hyphenated words: VGA-kaapelissa
        parts = string.rsplit("-", 1)
        
        lemma = self._lemmatize_compound(parts[-1], exceptions, univ_pos)

        if len(parts) == 1:
            return lemma
        else:
            return [parts[0] + "-" + lemma[0]]

    def _lemmatize_compound(self, string, exceptions, univ_pos):
        orig = string
        oov_forms = []
        forms = []

        analyses = self.voikko.analyze(string)
        base_and_pos = list(chain.from_iterable([
            self._baseform_and_pos(x, string) for x in analyses
        ]))
        matching_pos = [x for x in base_and_pos if x[1] == univ_pos]
        if univ_pos == ADV and analyses:
            oov_forms.append(self._normalize_adv(analyses[0], orig.lower()))
        elif matching_pos:
            forms.extend(x[0] for x in matching_pos)
        elif analyses:
            oov_forms.extend(x[0] for x in base_and_pos)

        forms = list(OrderedDict.fromkeys(forms))

        # Put exceptions at the front of the list, so they get priority.
        # This is a dodgy heuristic -- but it's the best we can do until we get
        # frequencies on this. We can at least prune out problematic exceptions,
        # if they shadow more frequent analyses.
        for exc in exceptions.get(orig.lower(), []):
            if exc not in forms:
                forms.insert(0, exc)
        if not forms:
            forms.extend(oov_forms)
        if not forms:
            forms.append(orig)
        return forms

    def _baseform_and_pos(self, analysis, orig):
        baseform = analysis.get("BASEFORM")
        voikko_class = analysis.get("CLASS")

        if (voikko_class == "teonsana" and
            analysis.get("MOOD") == "MINEN-infinitive"
        ):
            # MINEN infinitive
            form = self._fst_form(analysis, self.minen_re, "minen")
            if form:
                return [(form, NOUN)]
            else:
                return [(baseform, VERB)]

        elif (voikko_class == "laatusana" and
              analysis.get("PARTICIPLE") in ["past_active",
                                             "past_passive",
                                             "present_active",
                                             "present_passive"]
        ):
            # VA, NUT and TU participles
            return [
                (self._wordbase(analysis), VERB),
                (baseform, ADJ)
            ]

        elif (voikko_class == "nimisana" and
              analysis.get("PARTICIPLE") == "agent"
        ):
            # agent participle
            return [(self._wordbase(analysis), VERB)]

        elif (voikko_class in ["laatusana", "lukusana"] and
              analysis.get("SIJAMUOTO") == "kerrontosti"
        ):
            form = self._fst_form(analysis, self.sti_re, "sti")
            if form:
                return [(form, ADV)]
            else:
                return [(baseform, self.voikko_pos_to_upos[voikko_class])]

        elif voikko_class == "seikkasana" and orig.endswith("itse"):
            return [(orig, ADV)]

        elif voikko_class == "asemosana":
            lemma = self.pron_baseform_exceptions.get(baseform, baseform)
            return [(lemma, self.voikko_pos_to_upos[voikko_class])]

        elif voikko_class in self.voikko_pos_to_upos:
            return [(baseform, self.voikko_pos_to_upos[voikko_class])]

        else:
            return [(baseform, None)]

    def _fst_form(self, analysis, stem_re, suffix):
        fstoutput = analysis.get("FSTOUTPUT")
        ny_match = self.ny_re.search(fstoutput)
        if ny_match:
            return ny_match.group(1)

        fst_match = stem_re.search(fstoutput)
        if not fst_match:
            return None

        stem = fst_match.group(1)
        compounds = self.compound_re.findall(analysis.get("WORDBASES"))
        if len(compounds) > 1:
            return "".join(compounds[:-1]) + stem + suffix
        else:
            return stem + suffix

    def _wordbase(self, analysis):
        wordbases = analysis.get("WORDBASES")
        num_bases = max(analysis.get("STRUCTURE", "").count("="), 1)

        i = 0
        forms = []
        for base in re.finditer(r"\+([^+]+)", wordbases):
            full_form = base.group(1)
            parentheses_match = re.search(r"(.+)\((.+)\)", full_form)
            if parentheses_match:
                k = parentheses_match.group(2).count("=") + 1
                if i < num_bases - k:
                    form = parentheses_match.group(1)
                else:
                    form = parentheses_match.group(2)
            else:
                form = full_form

            split = form.split("=")
            forms.extend(split)
            i += len(split)

            if i >= num_bases:
                break

        return ''.join(forms)

    def _normalize_adv(self, analysis, word):
        focus = analysis.get("FOCUS")
        kysymysliite = analysis.get("KYSYMYSLIITE")

        if focus and kysymysliite:
            k = 2
        elif focus or kysymysliite:
            k = 1
        else:
            k = 0
        for _ in range(k):
            if focus and word.endswith(focus):
                word = word[:-len(focus)]
            elif kysymysliite and (word.endswith("ko") or word.endswith("kö")):
                word = word[:-2]

        if analysis.get("POSSESSIVE") and not analysis.get("SIJAMUOTO"):
            return analysis.get("BASEFORM")
        else:
            return word


class VrtZipCorpus:
    """Iterate Doc objects from a ZIP file that contains VRT files.

    path (Path): The ZIP filename to read from.
    min_length (int): Minimum document length (in tokens). Shorter documents
        will be skipped. Defaults to 0, which indicates no limit.
    max_length (int): Maximum document length (in tokens). Longer documents will
        be skipped. Defaults to 0, which indicates no limit.
    limit (int): Limit corpus to a subset of examples, e.g. for debugging.
        Defaults to 0, which indicates no limit.
    """

    def __init__(
            self,
            path: Union[str, Path],
            *,
            limit: int = 0,
            min_length: int = 0,
            max_length: int = 0,
    ) -> None:
        self.path = util.ensure_path(path)
        self.limit = limit
        self.min_length = min_length
        self.max_length = max_length

    def __call__(self, nlp: "Language") -> Iterator[Example]:
        """Yield examples from the data.

        nlp (Language): The current nlp object.
        YIELDS (Example): The example objects.

        DOCS: https://spacy.io/api/corpus#jsonlcorpus-call
        """
        i = 0
        zf = ZipFile(self.path)
        vrt_names = [p for p in zf.namelist() if p.endswith('.VRT')]
        for nested in vrt_names:
            with zf.open(nested) as f:
                ftext = TextIOWrapper(f, encoding='utf-8')
                for text in self.vrt_extract_documents(ftext):
                    text = self.skip_title_line(text)
                    doc = nlp.make_doc(text)
                    if self.min_length >= 1 and len(doc) < self.min_length:
                        continue
                    elif self.max_length >= 1 and len(doc) >= self.max_length:
                        continue
                    else:
                        words = [w.text for w in doc]
                        spaces = [bool(w.whitespace_) for w in doc]
                        # We don't *need* an example here, but it seems nice to
                        # make it match the Corpus signature.
                        yield Example(doc, Doc(nlp.vocab, words=words, spaces=spaces))

                    i += 1
                    if self.limit >= 1 and i >= self.limit:
                        return


    def vrt_extract_documents(self, fileobj):
        tokens = []
        quote_active = False
        paragraph_break = False
        for line in fileobj:
            if line.startswith('</doc'):
                # end of document
                yield ''.join(tokens)

                tokens = []
                quote_active = False
                paragraph_break = False

            elif line.startswith('</paragraph'):
                # paragraph break
                quote_active = False
                paragraph_break = True

            elif line.startswith('<'):
                # ignored document structure
                pass

            else:
                # content
                fields = line.split('\t')
                term = fields[1]

                if not tokens:
                    pass
                elif paragraph_break:
                    tokens.append('\n\n')
                elif not (self.char_is_in(term, '"”') and quote_active) \
                     and not (term == '’') \
                     and not (term.isdigit() and len(tokens) >= 2 and tokens[-2].isdigit() and self.char_is_in(tokens[-1], '.,')) \
                     and not self.char_is_in(term, '.,:;)]}') \
                     and not self.char_is_in(tokens[-1], '([{’') \
                     and not (self.char_is_in(tokens[-1], '"”') and quote_active):
                    tokens.append(' ')

                tokens.append(term)

                paragraph_break = False
                if self.char_is_in(term, '"”'):
                    quote_active = not quote_active
                elif not quote_active and len(term) > 1 and self.char_is_in(term[0], '"”'):
                    # Sometimes the starting quote is not tokenized as a
                    # separate token
                    quote_active = True

        if tokens:
            # We end up here if the last document wasn't terminated
            # properly with </doc>
            yield ''.join(tokens)

    def skip_title_line(self, text):
        # The first line is the title, the second line is empty
        parts = text.split('\n', 2)
        if len(parts) < 3:
            return text
        else:
            assert len(parts[1]) == 0
            return parts[-1]

    def char_is_in(self, x, chars):
        return len(x) == 1 and any(x == c for c in chars)


def noun_chunks(doclike: Union[Doc, Span]) -> Iterator[Span]:
    """Detect base noun phrases from a dependency parse. Works on both Doc and Span."""
    labels = [
        "nsubj",
        "nsubj:cop",
        "obj",
        "obl",
        "ROOT",
    ]
    extend_labels = [
        "advmod",
        "amod",
        "appos",
        "case",
        "compound",
        "compound:nn",
        "flat:name",
        "nmod",
        "nmod:gobj",
        "nmod:gsubj",
        "nmod:poss",
        "nummod",
    ]

    def potential_np_head(word):
        # TODO: PRON handling is inconsistent. Should some pronouns
        # (indefinite?, personal?) be considered part of a noun chunk?
        return word.pos in (NOUN, PROPN) and (word.dep in np_deps or word.head.pos == PRON)

    doc = doclike.doc  # Ensure works on both Doc and Span.
    if not doc.has_annotation("DEP"):
        raise ValueError(Errors.E029)

    np_deps = [doc.vocab.strings[label] for label in labels]
    extend_deps = [doc.vocab.strings[label] for label in extend_labels]
    np_label = doc.vocab.strings.add("NP")
    conj_label = doc.vocab.strings.add("conj")

    rbracket = 0
    prev_end = -1
    for i, word in enumerate(doclike):
        if i < rbracket:
            continue

        # Is this a potential independent NP head or coordinated with
        # a NOUN that is itself an independent NP head?
        #
        # e.g. "Terveyden ja hyvinvoinnin laitos"
        if potential_np_head(word) or (word.dep == conj_label and potential_np_head(word.head)):
            # Try to extend to the left to include adjective/num
            # modifiers, compound words etc.
            lbracket = word.i
            for ldep in word.lefts:
                if ldep.pos in (NOUN, PROPN, NUM, ADJ) and ldep.dep in extend_deps:
                    lbracket = ldep.left_edge.i
                    break

            # Prevent nested chunks from being produced
            if lbracket <= prev_end:
                continue

            rbracket = word.i
            # Try to extend the span to the right to capture close
            # appositions and noun modifiers
            for rdep in word.rights:
                if rdep.dep in extend_deps:
                    rbracket = rdep.i
                    for j in range(rdep.i + 1, rdep.right_edge.i + 1):
                        if doc[j].dep in extend_deps:
                            rbracket = j
            prev_end = rbracket

            yield lbracket, rbracket + 1, np_label


@Finnish.factory(
    "lemmatizer",
    assigns=["token.lemma"],
    default_config={"model": None, "mode": "voikko", "overwrite": False},
    default_score_weights={"lemma_acc": 1.0},
)
def make_lemmatizer(
    nlp: Language, model: Optional[Model], name: str, mode: str, overwrite: bool = False
):
    return FinnishLemmatizer(nlp.vocab, name, overwrite)


@util.registry.misc("spacyfi.read_lookups_from_json.v1")
def create_lookups_from_json_reader(path: Path) -> Lookups:
    lookups = Lookups()
    for p in path.glob("*.json"):
        table_name = p.stem
        data = srsly.read_json(p)
        lookups.add_table(table_name, data)
    return lookups


@util.registry.readers("spacyfi.VrtZipCorpus.v1")
def create_vrt_zip_reader(
        path: Optional[Path], min_length: int = 0, max_length: int = 0, limit: int = 0
) -> Callable[["Language"], Iterable[Doc]]:
    if path is None:
        raise ValueError(Errors.E913)

    return VrtZipCorpus(
        path,
        limit=limit,
        min_length=min_length,
        max_length=max_length,
    )


class FinnishExDefaults(FinnishDefaults):
    syntax_iterators = {"noun_chunks": noun_chunks}


@util.registry.languages("fi")
class FinnishExtended(Language):
    """Extends the default Finnish language class with syntax iterators."""
    lang = 'fi'
    Defaults = FinnishExDefaults
