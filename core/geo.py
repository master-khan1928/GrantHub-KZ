"""Локация гранта: страна обучения (ISO-2) и страна, выдающая грант.

Раздел «Казахстан / Зарубеж» определяется только полем country_code, а не текстом.
Здесь — справочники и правила, по которым сканер назначает страну и решает,
нужно ли отправить запись на ручную проверку.
"""
import re
from typing import Optional

_BY_COUNTRY = {
    "US": ["Harvard University", "Stanford University", "Massachusetts Institute of Technology",
           "California Institute of Technology", "Princeton University", "Yale University", "University of Chicago",
           "University of Pennsylvania", "Columbia University", "Cornell University",
           "University of California, Berkeley", "University of California, Los Angeles", "University of Michigan",
           "Johns Hopkins University", "Duke University", "Northwestern University", "Boston University",
           "New York University", "University of Texas at Austin", "Georgia Institute of Technology",
           "University of Illinois Urbana-Champaign", "University of Wisconsin-Madison", "University of Washington",
           "Carnegie Mellon University", "Purdue University", "University of California, San Diego",
           "University of California, Davis", "Ohio State University", "Pennsylvania State University",
           "University of Minnesota", "Rice University", "Vanderbilt University", "University of Southern California",
           "University of Notre Dame", "Georgetown University", "Brown University", "Dartmouth College",
           "University of Virginia", "University of North Carolina at Chapel Hill", "Michigan State University",
           "Arizona State University"],
    "GB": ["University of Oxford", "University of Cambridge", "Imperial College London", "University of Edinburgh",
           "King's College London", "London School of Economics", "University College London", "University of Manchester"],
    "CA": ["University of Toronto", "McGill University", "University of British Columbia", "University of Waterloo",
           "Queen's University", "University of Alberta", "University of Montreal"],
    "AU": ["University of Melbourne", "University of Sydney", "Australian National University"],
    "CH": ["ETH Zurich", "EPFL", "University of Zurich"],
    "FR": ["Sciences Po", "Sorbonne University"],
    "DE": ["Ludwig Maximilian University of Munich", "Technical University of Munich", "Heidelberg University",
           "Humboldt University of Berlin", "Free University of Berlin"],
    "NL": ["University of Amsterdam", "Delft University of Technology", "Leiden University", "Utrecht University"],
    "BE": ["KU Leuven"],
    "DK": ["University of Copenhagen"],
    "SE": ["Karolinska Institute", "Uppsala University", "Lund University"],
    "FI": ["University of Helsinki"],
    "NO": ["University of Oslo"],
    "AT": ["University of Vienna"],
    "PL": ["University of Warsaw"],
    "CZ": ["Charles University"],
    "IT": ["University of Bologna", "Sapienza University of Rome", "Politecnico di Milano"],
    "ES": ["Universidad Autonoma de Madrid", "Universidad Complutense de Madrid", "University of Barcelona",
           "Pompeu Fabra University"],
    "SG": ["National University of Singapore", "Nanyang Technological University"],
    "HK": ["University of Hong Kong", "Hong Kong University of Science and Technology", "Chinese University of Hong Kong"],
    "CN": ["Peking University", "Tsinghua University", "Fudan University", "Shanghai Jiao Tong University"],
    "KR": ["Seoul National University", "KAIST", "Yonsei University", "Korea University", "Sungkyunkwan University",
           "Hanyang University"],
    "JP": ["University of Tokyo", "Kyoto University", "Osaka University", "Tokyo Institute of Technology",
           "Waseda University", "Keio University"],
    "TW": ["National Taiwan University"],
    "IN": ["Indian Institute of Technology Bombay", "Indian Institute of Technology Delhi", "Indian Institute of Science"],
    "MY": ["University of Malaya", "Universiti Teknologi Malaysia"],
    "TH": ["Chulalongkorn University", "Mahidol University"],
    "LB": ["American University of Beirut"],
    "SA": ["King Abdullah University of Science and Technology", "King Fahd University of Petroleum and Minerals",
           "King Saud University"],
    "QA": ["Qatar University"],
    "AE": ["Khalifa University", "United Arab Emirates University", "American University of Sharjah"],
    "ZA": ["University of Cape Town", "University of the Witwatersrand", "Stellenbosch University"],
    "EG": ["American University in Cairo", "Cairo University"],
    "KE": ["University of Nairobi"],
    "UG": ["Makerere University"],
    "BR": ["University of Sao Paulo", "Universidade Estadual de Campinas"],
    "CL": ["Pontificia Universidad Catolica de Chile"],
    "AR": ["Universidad de Buenos Aires"],
    "MX": ["Universidad Nacional Autonoma de Mexico", "Tecnologico de Monterrey"],
    "JM": ["University of the West Indies"],
    "NZ": ["University of Auckland", "University of Otago"],
    "IE": ["Trinity College Dublin", "University College Dublin"],
    "KZ": ["Nazarbayev University", "Al-Farabi Kazakh National University", "Eurasian National University",
           "Kazakh-British Technical University", "Suleyman Demirel University", "KIMEP University",
           "Almaty Management University", "Satbayev University", "Astana IT University", "Narxoz University",
           "Maqsut Narikbayev University", "International IT University Almaty", "International IT University",
           "Kazakh-German University", "Turan University", "Asfendiyarov Kazakh National Medical University",
           "Karaganda Buketov University", "Abai Kazakh National Pedagogical University",
           "Auezov South Kazakhstan University", "Toraighyrov University", "Министерство образования РК"],
}
# Университет (источник сканера) -> страна, где он находится
UNIVERSITY_COUNTRY = {name: cc for cc, names in _BY_COUNTRY.items() for name in names}

# Программа (источник сканера) -> (кто выдаёт грант, где проходит учёба); None = несколько стран
PROGRAM_COUNTRY = {
    "Bolashak scholarship": ("KZ", None), "Yessenov Foundation scholarship": ("KZ", None),
    "Open Doors Russian Scholarship Project": ("RU", "RU"), "Abai-Verne scholarship France Kazakhstan": ("FR", "FR"),
    "Fulbright Foreign Student Program": ("US", "US"), "Hubert H. Humphrey Fellowship": ("US", "US"),
    "Global UGRAD program": ("US", "US"), "Knight-Hennessy Scholars": ("US", "US"),
    "Schwarzman Scholars": ("CN", "CN"), "Yenching Academy scholarship": ("CN", "CN"),
    "Chevening scholarship": ("GB", "GB"), "Commonwealth Scholarship": ("GB", "GB"), "Rhodes Scholarship": ("GB", "GB"),
    "Gates Cambridge scholarship": ("GB", "GB"), "Clarendon Scholarship Oxford": ("GB", "GB"),
    "Weidenfeld-Hoffmann Scholarships": ("GB", "GB"),
    "Government of Ireland International Education Scholarship": ("IE", "IE"),
    "DAAD scholarship": ("DE", "DE"), "Eiffel Excellence Scholarship": ("FR", "FR"),
    "Swedish Institute Scholarships for Global Professionals": ("SE", "SE"), "Stipendium Hungaricum": ("HU", "HU"),
    "Swiss Government Excellence Scholarships": ("CH", "CH"), "Holland Scholarship": ("NL", "NL"),
    "Orange Tulip Scholarship": ("NL", "NL"), "Italian Government Scholarship foreign students": ("IT", "IT"),
    "Turkiye Burslari scholarship": ("TR", "TR"), "Romanian Government Scholarship": ("RO", "RO"),
    "Finland Scholarship master": ("FI", "FI"), "Danish Government Scholarship": ("DK", "DK"),
    "Vienna Biocenter PhD program": ("AT", "AT"), "Polish NAWA scholarship": ("PL", "PL"),
    "Czech Government Scholarship": ("CZ", "CZ"), "Estonian Government scholarship": ("EE", "EE"),
    "Konrad Adenauer Stiftung scholarship": ("DE", "DE"), "Heinrich Boll Foundation scholarship": ("DE", "DE"),
    "Friedrich Ebert Stiftung scholarship": ("DE", "DE"), "MEXT scholarship Japan": ("JP", "JP"),
    "Global Korea Scholarship GKS": ("KR", "KR"), "Chinese Government Scholarship CSC": ("CN", "CN"),
    "Taiwan ICDF scholarship": ("TW", "TW"), "Singapore International Graduate Award": ("SG", "SG"),
    "Brunei Darussalam Government Scholarship": ("BN", "BN"), "Australia Awards scholarship": ("AU", "AU"),
    "Manaaki New Zealand Scholarship": ("NZ", "NZ"), "Hong Kong PhD Fellowship Scheme": ("HK", "HK"),
    "Malaysia International Scholarship": ("MY", "MY"), "KAUST Fellowship": ("SA", "SA"),
    "Qatar University international scholarship": ("QA", "QA"), "Kuwait Government scholarship": ("KW", "KW"),
    "Vanier Canada Graduate Scholarships": ("CA", "CA"), "Lester B. Pearson International Scholarship": ("CA", "CA"),
    "Emirates Diplomatic Academy scholarship": ("AE", "AE"), "Central European University scholarship": ("AT", "AT"),
    "American University of Central Asia scholarship": ("KG", "KG"), "OSCE Academy scholarship": ("KG", "KG"),
    "Nazarbayev University grant admission": ("KZ", "KZ"), "Ministry of Education Kazakhstan state grant": ("KZ", "KZ"),
}

# Названия стран для поиска: запрос «Германия» превращается в фильтр country_code = 'DE', а не в поиск по тексту
_COUNTRY_NAMES = {
    "KZ": ("казахстан", "қазақстан", "kazakhstan"), "US": ("сша", "америка", "usa", "united states"),
    "GB": ("великобритания", "англия", "британия", "uk", "united kingdom", "britain", "england"),
    "DE": ("германия", "germany"), "FR": ("франция", "france"), "IT": ("италия", "italy"), "ES": ("испания", "spain"),
    "NL": ("нидерланды", "голландия", "netherlands", "holland"), "CH": ("швейцария", "switzerland"),
    "AT": ("австрия", "austria"), "BE": ("бельгия", "belgium"), "SE": ("швеция", "sweden"),
    "FI": ("финляндия", "finland"), "NO": ("норвегия", "norway"), "DK": ("дания", "denmark"),
    "PL": ("польша", "poland"), "CZ": ("чехия", "czechia", "czech republic"), "HU": ("венгрия", "hungary"),
    "RO": ("румыния", "romania"), "EE": ("эстония", "estonia"), "IE": ("ирландия", "ireland"),
    "TR": ("турция", "turkey", "türkiye", "turkiye"), "RU": ("россия", "russia"), "CN": ("китай", "china"),
    "JP": ("япония", "japan"), "KR": ("корея", "южная корея", "korea", "south korea"), "SG": ("сингапур", "singapore"),
    "HK": ("гонконг", "hong kong"), "TW": ("тайвань", "taiwan"), "MY": ("малайзия", "malaysia"),
    "IN": ("индия", "india"), "AU": ("австралия", "australia"), "NZ": ("новая зеландия", "new zealand"),
    "CA": ("канада", "canada"), "AE": ("оаэ", "эмираты", "uae"), "QA": ("катар", "qatar"),
    "SA": ("саудовская аравия", "saudi arabia"), "KG": ("кыргызстан", "киргизия", "kyrgyzstan"),
}
COUNTRY_BY_NAME = {name: cc for cc, names in _COUNTRY_NAMES.items() for name in names}

_TLD_COUNTRY = {"kz": "KZ", "de": "DE", "fr": "FR", "it": "IT", "es": "ES", "nl": "NL", "ch": "CH", "at": "AT",
                "be": "BE", "se": "SE", "fi": "FI", "no": "NO", "dk": "DK", "pl": "PL", "cz": "CZ", "hu": "HU",
                "ro": "RO", "ee": "EE", "ie": "IE", "tr": "TR", "ru": "RU", "cn": "CN", "jp": "JP", "kr": "KR",
                "sg": "SG", "hk": "HK", "tw": "TW", "my": "MY", "au": "AU", "nz": "NZ", "ca": "CA", "uk": "GB"}
_ISO2_RE = re.compile(r"^[A-Z]{2}$")
_ALIASES = {"UK": "GB", "EN": "GB"}
# многостранные «коды», которые модель любит подставлять вместо страны
_NOT_A_COUNTRY = {"EU", "XX", "ZZ", "UN", "NA"}
_KZ_OUTBOUND_RE = re.compile(r"болашак|bolashak|есенов|yessenov", re.I)


def flag_emoji(country_code) -> str:
    """ISO-код -> эмодзи флага из региональных символов Unicode: 'KZ' -> 🇰🇿. Нет кода — пустая строка."""
    code = normalize_country(country_code)
    return "".join(chr(127397 + ord(ch)) for ch in code) if code else ""


def normalize_country(value) -> Optional[str]:
    """'de' / 'UK' / ' kz ' -> ISO-2 в верхнем регистре; мусор и «EU» -> None."""
    if not isinstance(value, str):
        return None
    code = _ALIASES.get(value.strip().upper(), value.strip().upper())
    if not _ISO2_RE.match(code) or code in _NOT_A_COUNTRY:
        return None
    return code


def domain_country(domain: str) -> Optional[str]:
    """Страна по национальному домену (kbtu.edu.kz -> KZ). Для .com/.org/.edu — None."""
    return _TLD_COUNTRY.get((domain or "").rsplit(".", 1)[-1].lower())


def resolve_location(country, provider, category, source, domain: str, name: str = "") -> tuple:
    """-> (country_code, provider_country, doubts).

    country/provider/category — то, что сказала модель (или старая запись); source — источник сканера;
    domain — домен ссылки. Жёсткие данные (источник) важнее слов модели. doubts — причины, по которым
    запись нельзя публиковать без проверки оператором; пустой список = всё сходится.
    """
    llm_cc, llm_provider = normalize_country(country), normalize_country(provider)
    doubts = []
    tld_cc = domain_country(domain)

    if source in UNIVERSITY_COUNTRY:
        cc = UNIVERSITY_COUNTRY[source]
        provider_cc = llm_provider or cc
        if llm_cc and llm_cc != cc:
            doubts.append(f"модель указала страну {llm_cc}, а источник «{source}» находится в {cc}")
    elif source in PROGRAM_COUNTRY:
        provider_cc, dest = PROGRAM_COUNTRY[source]
        cc = dest or llm_cc
        if dest and llm_cc and llm_cc != dest:
            doubts.append(f"модель указала страну {llm_cc}, а программа «{source}» — это {dest}")
        if not dest and cc == "KZ" and provider_cc == "KZ":
            cc = None  # «Болашак»: выдаёт Казахстан, учёба за рубежом
    elif _KZ_OUTBOUND_RE.search(name or ""):
        cc, provider_cc = (llm_cc if llm_cc != "KZ" else None), "KZ"
    else:
        cc, provider_cc = llm_cc, llm_provider
        if cc is None and category == "kz":
            cc = "KZ"
            if tld_cc != "KZ":
                doubts.append("страна не указана, раздел «Казахстан» назначен только со слов модели")
        elif cc == "KZ" and tld_cc != "KZ":
            doubts.append("страна KZ не подтверждена ни источником, ни доменом .kz")
        elif cc != "KZ" and tld_cc == "KZ":
            doubts.append(f"сайт в зоне .kz, но страна обучения — {cc or 'не указана'}")

    if source not in PROGRAM_COUNTRY and not _KZ_OUTBOUND_RE.search(name or ""):
        if category == "kz" and cc != "KZ":
            doubts.append(f"модель отнесла грант к Казахстану, но страна обучения — {cc or 'не указана'}")
        elif category == "abroad" and cc == "KZ":
            doubts.append("модель отнесла грант к зарубежным, но страна обучения — KZ")
    return cc, provider_cc or None, doubts
