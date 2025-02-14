import pytest
import spacy.util
from fi import FinnishExtended
from util import get_doc_from_text

fi_nlp = FinnishExtended()
fi_tokenizer = fi_nlp.tokenizer


FI_NP_TEST_EXAMPLES = [
    (
        'Kaksi tyttöä potkii punaista palloa',
        ['NUM', 'NOUN', 'VERB', 'ADJ', 'NOUN'],
        ['nummod', 'nsubj', 'ROOT', 'amod', 'obj'],
        [1, 1, 0, 1, -2],
        ['Kaksi tyttöä', 'punaista palloa'],
    ),
    (
        'Erittäin vaarallinen leijona karkasi kiertävän sirkuksen eläintenkesyttäjältä',
        ['ADV', 'ADJ', 'NOUN', 'VERB', 'ADJ', 'NOUN', 'NOUN'],
        ['advmod', 'amod', 'nsubj', 'ROOT', 'amod', 'nmod:poss', 'obl'],
        [1, 1, 1, 0, 1, 1, -3],
        ['Erittäin vaarallinen leijona', 'kiertävän sirkuksen eläintenkesyttäjältä'],
    ),
    (
        'Leijona raidallisine tassuineen piileksii Porin kaupungin lähellä',
        ['NOUN', 'ADJ', 'NOUN', 'VERB', 'PROPN', 'NOUN', 'ADP'],
        ['nsubj', 'amod', 'nmod', 'ROOT', 'nmod:poss', 'obl', 'case'],
        [3, 1, -2, 0, 1, -2, -1],
        ['Leijona raidallisine tassuineen', 'Porin kaupungin lähellä'],
    ),
    (
        'Lounaalla nautittiin salaattia, maukasta kanaa ja raikasta vettä',
        ['NOUN', 'VERB', 'NOUN', 'PUNCT', 'ADJ', 'NOUN', 'CCONJ', 'ADJ', 'NOUN'],
        ['obl', 'ROOT', 'obj', 'punct', 'amod', 'conj', 'cc', 'amod', 'conj'],
        [1, 0, -1, 2, 1, -3, 2, 1, -6],
        ['Lounaalla', 'salaattia', 'maukasta kanaa', 'raikasta vettä'],
    ),
    (
        'Minua houkuttaa maalle muuttaminen talven jälkeen',
        ['PRON', 'VERB', 'NOUN', 'NOUN', 'NOUN', 'ADP'],
        ['obj', 'ROOT', 'nmod', 'nsubj', 'nmod', 'case'],
        [1, 0, 1, -2, -1, -1],
        ['maalle muuttaminen talven jälkeen'],
    ),
    (
        'Päivän kohokohta oli vierailu museossa kummilasten kanssa',
        ['NOUN', 'NOUN', 'AUX', 'NOUN', 'NOUN', 'NOUN', 'ADP'],
        ['nmod:poss', 'nsubj:cop', 'cop', 'ROOT', 'nmod', 'nmod', 'case'],
        [1, 2, 1, 0, -1, -1, -1],
        ['Päivän kohokohta', 'vierailu museossa kummilasten kanssa'],
    ),
    (
        'Yrittäjät maksoivat tuomioistuimen määräämät korvaukset',
        ['NOUN', 'VERB', 'NOUN', 'VERB', 'NOUN'],
        ['nsubj', 'ROOT', 'nsubj', 'acl', 'obj'],
        [1, 0, 1, 1, -3],
        ['Yrittäjät', 'tuomioistuimen', 'korvaukset'],
    ),
    (
        'Julkisoikeudelliset tai niihin rinnastettavat saatavat ovat suoraan ulosottokelpoisia',
        ['ADJ', 'CCONJ', 'PRON', 'VERB', 'NOUN', 'AUX', 'ADV', 'NOUN'],
        ['amod', 'cc', 'obl', 'acl', 'nsubj:cop', 'cop', 'advmod', 'ROOT'],
        [4, 3, 1, 1, 3, 2, 1, 0],
        ['Julkisoikeudelliset tai niihin rinnastettavat saatavat', 'ulosottokelpoisia'],
    ),
    (
        'Se oli ala-arvoista käytöstä kaikilta oppilailta, myös valvojaoppilailta',
        ['PRON', 'AUX', 'ADJ', 'NOUN', 'PRON', 'NOUN', 'PUNCT', 'ADV', 'NOUN'],
        ['nsubj:cop', 'cop', 'amod', 'ROOT', 'det', 'nmod', 'punct', 'advmod', 'appos'],
        [3, 2, 1, 0, 1, -2, 2, 1, -3],
        ['ala-arvoista käytöstä kaikilta oppilailta , myös valvojaoppilailta'],
    ),
    (
        'Isä souti veneellä, jonka hän oli vuokrannut',
        ['NOUN', 'VERB', 'NOUN', 'PUNCT', 'PRON', 'PRON', 'AUX', 'VERB'],
        ['nsubj', 'ROOT', 'obl', 'punct', 'obj', 'nsubj', 'aux', 'acl:relcl'],
        [1, 0, -1, 4, 3, 2, 1, -5],
        ['Isä', 'veneellä'],
    ),
    (
        'Kirja, jonka poimin hyllystä, kertoo norsuista',
        ['NOUN', 'PUNCT', 'PRON', 'VERB', 'NOUN', 'PUNCT', 'VERB', 'NOUN'],
        ['nsubj', 'punct', 'obj', 'acl:relcl', 'obl', 'punct', 'ROOT', 'obl'],
        [6, 2, 1, -3, -1, 1, 0, -1],
        ['Kirja', 'hyllystä', 'norsuista'],
    ),
    (
        'Huomenna on päivä, jota olemme odottaneet',
        ['NOUN', 'AUX', 'NOUN', 'PUNCT', 'PRON', 'AUX', 'VERB'],
        ['ROOT', 'cop', 'nsubj:cop', 'punct', 'obj', 'aux', 'acl:relcl'],
        [0, -1, -2, 3, 2, 1, -4],
        ['Huomenna', 'päivä'],
    ),
    (
        'Liikkuvuuden lisääminen on yksi korkeakoulutuksen keskeisistä kehittämiskohteista',
        ['NOUN', 'NOUN', 'AUX', 'PRON', 'NOUN', 'ADJ', 'NOUN'],
        ['nmod:gobj', 'nsubj:cop', 'cop', 'ROOT', 'nmod:poss', 'amod', 'nmod'],
        [1, 2, 1, 0, 2, 1, -3],
        ['Liikkuvuuden lisääminen', 'korkeakoulutuksen keskeisistä kehittämiskohteista'],

    ),
    (
        'Kaupalliset palvelut jätetään yksityisten palveluntarjoajien tarjottavaksi',
        ['ADJ', 'NOUN', 'VERB', 'ADJ', 'NOUN', 'NOUN'],
        ['amod', 'obj', 'ROOT', 'amod', 'nmod:gsubj', 'obl'],
        [1, 1, 0, 1, 1, -3],
        ['Kaupalliset palvelut', 'yksityisten palveluntarjoajien tarjottavaksi'],
    ),
    (
        'New York tunnetaan kaupunkina, joka ei koskaan nuku',
        ['PROPN', 'PROPN', 'VERB', 'NOUN', 'PUNCT', 'PRON', 'AUX', 'ADV', 'VERB'],
        ['obj', 'flat:name', 'ROOT', 'obl', 'punct', 'nsubj', 'aux', 'advmod', 'acl:relcl'],
        [2, -1, 0, -1, 4, 3, 2, 1, -5],
        ['New York', 'kaupunkina'],
    ),
    (
        'Loput vihjeet saat herra Möttöseltä',
        ['NOUN', 'NOUN', 'VERB', 'NOUN', 'PROPN'],
        ['compound:nn', 'obj', 'ROOT', 'compound:nn', 'obj'],
        [1, 1, 0, 1, -2],
        ['Loput vihjeet', 'herra Möttöseltä'],
    ),
    (
        'mahdollisuus tukea muita päivystysyksiköitä',
        ['NOUN', 'VERB', 'PRON', 'NOUN'],
        ['ROOT', 'acl', 'det', 'obj'],
        [0, -1, 1, -2],
        ['mahdollisuus', 'päivystysyksiköitä'],
    ),
    (
        'sairaanhoitopiirit harjoittavat leikkaustoimintaa alueellaan useammassa sairaalassa',
        ['NOUN', 'VERB', 'NOUN', 'NOUN', 'ADJ', 'NOUN'],
        ['nsubj', 'ROOT', 'obj', 'obl', 'amod', 'obl'],
        [1, 0, -1, -1, 1, -3],
        ['sairaanhoitopiirit', 'leikkaustoimintaa', 'alueellaan', 'useammassa sairaalassa'],
    ),
    (
        'Lain mukaan varhaiskasvatus on suunnitelmallista toimintaa',
        ['NOUN', 'ADP', 'NOUN', 'AUX', 'ADJ', 'NOUN'],
        ['obl', 'case', 'nsubj:cop', 'cop', 'amod', 'ROOT'],
        [5, -1, 3, 2, 1, 0],
        ['Lain mukaan', 'varhaiskasvatus', 'suunnitelmallista toimintaa'],
    ),
]

FI_NP_TEST_EXAMPLES_APPOS = [
    (
        'Terveyden ja hyvinvoinnin laitos (THL) johtaa hanketta',
        ['NOUN', 'CCONJ', 'NOUN', 'NOUN', 'PUNCT', 'PROPN', 'PUNCT', 'VERB', 'NOUN'],
        ['nmod:poss', 'cc', 'conj', 'nsubj', 'punct', 'appos', 'punct', 'ROOT', 'obj'],
        [3, 1, -2, 4, 1, -2, -1, 0, -1],
        ['Terveyden ja hyvinvoinnin laitos ( THL )', 'hanketta'],
    ),
]


FI_NP_TEST_EXAMPLES_MULTI_SENTENCE = [
    (
        'Ilmassa on kevättä. Rännit tippuvat ja katuojat juoksevat',
        ['NOUN', 'AUX', 'NOUN', 'PUNCT', 'NOUN', 'VERB', 'CCONJ', 'NOUN', 'VERB'],
        ['ROOT', 'cop', 'nsubj:cop', 'punct', 'nsubj', 'ROOT', 'cc', 'nsubj', 'conj'],
        [0, -1, -2, -3, 1, 0, 2, 1, -3],
        [
            ['Ilmassa', 'kevättä'],
            ['Rännit', 'katuojat']
        ],
    ),
]


@pytest.mark.parametrize(
    "text,pos,deps,heads,expected_noun_chunks", FI_NP_TEST_EXAMPLES
)
def test_fi_noun_chunks(text, pos, deps, heads, expected_noun_chunks):
    doc = get_doc_from_text(text, fi_tokenizer, pos=pos, heads=heads, deps=deps)
    noun_chunks = list(doc.noun_chunks)

    assert len(noun_chunks) == len(expected_noun_chunks)
    for i, np in enumerate(noun_chunks):
        assert np.text == expected_noun_chunks[i]


@pytest.mark.xfail
@pytest.mark.parametrize(
    "text,pos,deps,heads,expected_noun_chunks", FI_NP_TEST_EXAMPLES_APPOS
)
def test_fi_noun_chunks_appos(text, pos, deps, heads, expected_noun_chunks):
    doc = get_doc_from_text(text, fi_tokenizer, pos=pos, heads=heads, deps=deps)
    noun_chunks = list(doc.noun_chunks)

    assert len(noun_chunks) == len(expected_noun_chunks)
    for i, np in enumerate(noun_chunks):
        assert np.text == expected_noun_chunks[i]


@pytest.mark.parametrize(
    "text,pos,deps,heads,expected_noun_chunks", FI_NP_TEST_EXAMPLES_MULTI_SENTENCE
)
def test_fi_noun_chunks_multiple_sentences(text, pos, deps, heads, expected_noun_chunks):
    doc = get_doc_from_text(text, fi_tokenizer, pos=pos, heads=heads, deps=deps)

    for s, expected in zip(doc.sents, expected_noun_chunks):
        noun_chunks = list(s.noun_chunks)
        assert len(noun_chunks) == len(expected)
        for i, np in enumerate(noun_chunks):
            assert np.text == expected[i]
