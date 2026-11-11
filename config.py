"""설정값. API 키는 .env 파일에서 읽습니다."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).parent

# 네이버 쇼핑 카테고리: 화장품/미용
BEAUTY_CID = "50000002"

# 타깃 성별: "f" = 여성, "m" = 남성, "" = 전체
# 성별을 바꾸면 DB 파일도 따로 쓰므로 데이터가 섞이지 않습니다.
GENDER = "f"
GENDER_LABEL = {"f": "여성", "m": "남성", "": ""}[GENDER]

# 데이터랩 연령 코드 -> 표시 이름
AGE_GROUPS = {
    "10": "10대",
    "20": "20대",
    "30": "30대",
    "40": "40대",
    "50": "50대",
    "60": "60대 이상",
}

TOP_N = 50                # 연령별로 이유를 분석하고 순위표에 보여줄 순위 수
COLLECT_N = 100           # 검색·품목·브랜드용으로 모아 두는 순위 수 (연령당 요청 5번)
RISE_THRESHOLD = 5        # 전일 대비 이만큼 이상 오르면 '급상승'
REUSE_DAYS = 7            # 순위가 안정적인 키워드는 최근 N일 내 분석을 재사용
EVIDENCE_DAYS = 5         # 근거 자료(뉴스/블로그) 수집 기간
COMMON_MIN_AGES = 4       # 이 이상 연령대에 동시에 오른 키워드 = '전 연령 공통'

# 원인 분류 (LLM이 이 중 하나만 고르도록 강제)
CATEGORIES = [
    "셀럽/광고",
    "시즌/날씨",
    "할인/행사",
    "성분/기술 트렌드",
    "SNS 바이럴",
    "신제품 출시",
    "스테디셀러",
    "원인 불명확",
]

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
# 네이버 검색 API 방식
#   "hub"    = 네이버 클라우드 플랫폼의 NAVER API HUB에서 받은 키 (2026년 6월부터 새로 발급받는 키)
#   "legacy" = 예전 네이버 개발자센터에서 받은 키 (2027년 6월 30일까지 사용 가능하다고 안내됨)
# 키가 비어 있으면 근거 검색 없이 순위만 모으는 '키 없이 쓰기' 모드로 돌아가요.
NAVER_API_MODE = os.getenv("NAVER_API_MODE", "hub")
HAS_SEARCH = bool(NAVER_CLIENT_ID and NAVER_CLIENT_SECRET)

# 브랜드 자동 추정에서 브랜드로 보지 않을 첫 단어 (매장·일반 수식어)
BRAND_STOPWORDS = ["올리브영", "다이소", "쿠팡", "무신사", "남자", "여자", "남성", "여성", "남자용", "여성용",
                   "어린이", "아기", "임산부", "천연", "비건", "대용량", "미니", "추천", "순위", "선물", "세트",
                   "겨울", "여름", "가을", "봄", "민감성", "지성", "건성", "수부지", "피부과", "약국", "약산성"]
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# 분석 방식: "free" = 무료(규칙 기반, AI 비용 없음) / "claude" = Claude API(유료, 더 자연스러운 문장)
ANALYZER = os.getenv("ANALYZER", "free")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

# 뷰티 팝업스토어·행사 수집용 검색어 (네이버 뉴스·블로그)
EVENT_QUERIES = [
    "뷰티 팝업스토어", "화장품 팝업스토어", "코스메틱 팝업", "뷰티 브랜드 팝업", "화장품 팝업 오픈",
    "성수 뷰티 팝업", "성수 화장품 팝업", "더현대 뷰티 팝업", "여의도 팝업 화장품", "올리브영 팝업",
    "무신사 뷰티 팝업", "향수 팝업스토어", "메이크업 팝업", "스킨케어 팝업", "뷰티 팝업 사전예약",
]
EVENT_DAYS = 10           # 행사 기사·글을 찾는 기간
EVENT_MAX_SOURCES = 40    # 한 번에 AI에게 넘길 기사·글 수

# 품목 분류: 위에서부터 차례로 검사해서 처음 맞는 품목으로 정합니다 (구체적인 것을 위에)
PRODUCT_CATEGORIES = [
    ("선케어",        ["선크림", "선스틱", "선쿠션", "선세럼", "선젤", "선로션", "자외선", "톤업"]),
    ("클렌징",        ["클렌징", "클렌저", "폼클", "필링", "각질", "리무버"]),
    ("베이스",        ["쿠션", "파운데이션", "컨실러", "프라이머", "픽서", "비비", "파우더", "팩트"]),
    ("마스크팩",      ["마스크팩", "시트팩", "패치", "수면팩", "워시오프", "모델링팩", "젤리팩"]),
    ("헤어",          ["헤어", "샴푸", "린스", "트리트먼트", "두피", "탈모", "고데기", "드라이기", "에어랩", "염색", "왁스"]),
    ("바디",          ["바디", "핸드크림", "풋", "데오", "입욕", "때필링"]),
    ("향수",          ["향수", "퍼퓸", "오드", "코롱", "프래그런스"]),
    ("네일",          ["네일", "매니큐어", "페디큐어"]),
    ("뷰티디바이스",  ["디바이스", "LED", "괄사", "에이지알", "부스터", "마사지기", "갈바닉"]),
    ("립",            ["립", "틴트", "글로스", "루즈"]),
    ("아이·브로우",   ["마스카라", "아이라이너", "섀도우", "섀도", "아이브로우", "눈썹", "속눈썹", "래쉬"]),
    ("치크·하이라이터", ["블러셔", "블러쉬", "치크", "하이라이터", "쉐딩", "컨투어"]),
    ("스킨케어",      ["세럼", "앰플", "에센스", "크림", "토너", "패드", "로션", "미스트", "스킨", "레티놀",
                       "PDRN", "니들", "콜라겐", "시카", "비타민", "수분", "보습", "주름", "탄력", "기미", "미백", "오일"]),
]

# 관심 브랜드: 지원하고 싶은 회사의 브랜드를 적어 두면 홈페이지에서 매일 따로 추적해요.
# 지원 브랜드(메디큐브) + 비교용 경쟁 브랜드
#   달바: 화장품+디바이스, 전략이 가장 비슷 / 톰: 디바이스 직접 경쟁 / 리쥬란: PDRN·디바이스 양쪽 비교
WATCH_BRANDS = ["메디큐브", "달바", "톰", "리쥬란"]
_wf = BASE_DIR / "watch_brands.txt"          # 이 파일이 있으면 위 목록 대신 이 파일을 씀 (GitHub에서 고치기 쉬움)
if _wf.exists():
    WATCH_BRANDS = [l.strip() for l in _wf.read_text(encoding="utf-8").splitlines() if l.strip() and not l.strip().startswith("#")]

# 디바이스 관심도(디지털/가전 분야)에서 브랜드 대신 검색할 대표 디바이스 이름
DEVICE_TERMS = {"메디큐브": "에이지알"}

# 자동 판별이 틀렸을 때 직접 고치는 곳 (python main.py --check 로 오늘 결과를 확인)
BRAND_OVERRIDES = {}       # 예: {"선크림": None}  (검색어 하나를 정확히 지정)

# 브랜드 이름 없이 검색되는 대표 상품·라인 이름 → 브랜드
# 이 말이 들어간 검색어는 모두 그 브랜드로 묶어요. 지원 브랜드의 대표 제품명을 계속 추가하세요.
BRAND_ALIASES = {
    "메디큐브": ["에이지알", "AGE-R", "agr", "부스터프로", "부스터 프로", "제로모공패드", "PDRN 핑크", "핑크 콜라겐"],
}
CATEGORY_OVERRIDES = {}    # 예: {"톤업크림": "베이스"}

# 광고·체험단 글로 보고 원인 근거에서 빼는 표현
AD_MARKERS = ["체험단", "협찬", "원고료", "제공받아", "제공 받아", "소정의", "유료광고", "광고 포함", "#광고", "업체로부터",
              "[광고]", "(광고)", "광고]", "[AD]", "[협찬]", "서포터즈"]

SITE_DAYS = 30            # 홈페이지에 담을 최근 날짜 수

DB_PATH = BASE_DIR / (f"beauty_trend_{GENDER}.db" if GENDER else "beauty_trend.db")
REPORT_DIR = BASE_DIR / "reports"


def alias_brand(keyword: str):
    """BRAND_ALIASES 에 걸리는 검색어면 그 브랜드 이름을, 아니면 None."""
    k = keyword.replace(" ", "").lower()
    for brand, words in BRAND_ALIASES.items():
        if any(w.replace(" ", "").lower() in k for w in words):
            return brand
    return None


def _load_known_brands():
    """brands_known.txt → [(찾을 이름(소문자·공백 제거), 표시 이름)], 긴 이름부터."""
    path = BASE_DIR / "brands_known.txt"
    pairs = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, _, others = line.partition("=")
            name = name.strip()
            for alias in [name] + [o.strip() for o in others.split(",") if o.strip()]:
                pairs.append((alias.replace(" ", "").lower(), name))
    return sorted(pairs, key=lambda x: -len(x[0]))


KNOWN_BRANDS = _load_known_brands()


def brand_in_text(text: str):
    """글 안에 들어 있는 알려진 브랜드 이름(가장 긴 것). 1글자 이름은 오인이 많아 제외."""
    t = text.replace(" ", "").lower()
    for alias, name in KNOWN_BRANDS:
        if len(alias) >= 2 and alias in t:
            return name
    for name, words in BRAND_ALIASES.items():
        if any(w.replace(" ", "").lower() in t for w in words if len(w) >= 3):
            return name
    return None


def known_brand(keyword: str):
    """검색어가 알려진 브랜드 이름으로 시작하면 그 브랜드. 가장 긴 이름이 우선(예: 톰포드 > 톰)."""
    k = keyword.replace(" ", "").lower()
    for alias, name in KNOWN_BRANDS:
        if k.startswith(alias):
            return name
    return None
