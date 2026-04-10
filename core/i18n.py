"""core/i18n.py — UI translations: English + Arabic variants only."""
from __future__ import annotations

SUPPORTED_LANGUAGES = {
    "en":       {"label": "English",  "dir": "ltr", "flag": "🇬🇧"},
    "ar":       {"label": "العربية",  "dir": "rtl", "flag": "🇸🇦"},
    "ar-eg":    {"label": "مصري",     "dir": "rtl", "flag": "🇪🇬"},
    "ar-gulf":  {"label": "خليجي",    "dir": "rtl", "flag": "🇦🇪"},
}

RTL_LANGUAGES = {"ar", "ar-eg", "ar-gulf"}

TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── Navigation ────────────────────────────────────────────────
    "nav.dashboard":    {"en":"Dashboard",       "ar":"لوحة التحكم",   "ar-eg":"الداشبورد",     "ar-gulf":"لوحة القيادة"},
    "nav.generate":     {"en":"Generate",         "ar":"إنشاء محتوى",   "ar-eg":"اعمل محتوى",    "ar-gulf":"إنشاء"},
    "nav.strategy":     {"en":"Strategy",         "ar":"الاستراتيجية",  "ar-eg":"الاستراتيجية",  "ar-gulf":"الاستراتيجية"},
    "nav.insights":     {"en":"Insights",         "ar":"الرؤى",         "ar-eg":"الإنسايتس",     "ar-gulf":"التحليلات"},
    "nav.calendar":     {"en":"Calendar",         "ar":"التقويم",       "ar-eg":"الجدول",        "ar-gulf":"التقويم"},
    "nav.history":      {"en":"History",          "ar":"السجل",         "ar-eg":"السجل",         "ar-gulf":"السجل"},
    "nav.brands":       {"en":"Brands",           "ar":"العلامات",      "ar-eg":"البراندز",      "ar-gulf":"العلامات"},
    "nav.account":      {"en":"Account",          "ar":"الحساب",        "ar-eg":"الحساب",        "ar-gulf":"الحساب"},
    "nav.pricing":      {"en":"Upgrade",          "ar":"ترقية",         "ar-eg":"ترقية",         "ar-gulf":"ترقية"},
    "nav.admin":        {"en":"Admin",            "ar":"المشرف",        "ar-eg":"الأدمن",        "ar-gulf":"الإدارة"},
    "nav.logout":       {"en":"Sign out",         "ar":"تسجيل الخروج",  "ar-eg":"اخرج",          "ar-gulf":"خروج"},
    "nav.workspace":    {"en":"Workspace",        "ar":"مساحة العمل",   "ar-eg":"الووركسبيس",    "ar-gulf":"مساحة العمل"},
    "nav.admin_section":{"en":"Admin",            "ar":"إدارة",         "ar-eg":"أدمن",          "ar-gulf":"إدارة"},

    # ── Quota ─────────────────────────────────────────────────────
    "quota.label":      {"en":"Monthly Quota",    "ar":"الحصة الشهرية", "ar-eg":"الحصة الشهرية", "ar-gulf":"الحصة الشهرية"},
    "quota.used":       {"en":"used",             "ar":"مستخدم",        "ar-eg":"اتحط",          "ar-gulf":"مستخدم"},

    # ── Language ──────────────────────────────────────────────────
    "lang.label":       {"en":"Language",         "ar":"اللغة",         "ar-eg":"اللغة",         "ar-gulf":"اللغة"},

    # ── Actions ───────────────────────────────────────────────────
    "action.save":      {"en":"Save",             "ar":"حفظ",           "ar-eg":"احفظ",          "ar-gulf":"حفظ"},
    "action.cancel":    {"en":"Cancel",           "ar":"إلغاء",         "ar-eg":"كنسل",          "ar-gulf":"إلغاء"},
    "action.delete":    {"en":"Delete",           "ar":"حذف",           "ar-eg":"امسح",          "ar-gulf":"حذف"},
    "action.edit":      {"en":"Edit",             "ar":"تعديل",         "ar-eg":"عدّل",          "ar-gulf":"تعديل"},
    "action.view":      {"en":"View",             "ar":"عرض",           "ar-eg":"شوف",           "ar-gulf":"عرض"},
    "action.generate":  {"en":"Generate",         "ar":"إنشاء",         "ar-eg":"اعمل",          "ar-gulf":"إنشاء"},
    "action.new":       {"en":"New",              "ar":"جديد",          "ar-eg":"جديد",          "ar-gulf":"جديد"},
    "action.back":      {"en":"Back",             "ar":"رجوع",          "ar-eg":"ارجع",          "ar-gulf":"رجوع"},
    "action.approve":   {"en":"Approve",          "ar":"موافقة",        "ar-eg":"وافق",          "ar-gulf":"موافقة"},
    "action.export":    {"en":"Export",           "ar":"تصدير",         "ar-eg":"صدّر",          "ar-gulf":"تصدير"},
    "action.search":    {"en":"Search",           "ar":"بحث",           "ar-eg":"دوّر",          "ar-gulf":"بحث"},
    "action.filter":    {"en":"Filter",           "ar":"تصفية",         "ar-eg":"فلتر",          "ar-gulf":"تصفية"},
    "action.ban":       {"en":"Ban",              "ar":"حظر",           "ar-eg":"وقّف",          "ar-gulf":"حظر"},
    "action.unban":     {"en":"Unban",            "ar":"رفع الحظر",     "ar-eg":"ارجعه",         "ar-gulf":"رفع الحظر"},
    "action.impersonate":{"en":"Login as",        "ar":"الدخول كـ",     "ar-eg":"ادخل كـ",       "ar-gulf":"الدخول كـ"},

    # ── Status ────────────────────────────────────────────────────
    "status.completed": {"en":"Completed",        "ar":"مكتمل",         "ar-eg":"خلص",           "ar-gulf":"مكتمل"},
    "status.running":   {"en":"Running",          "ar":"جارٍ",          "ar-eg":"شغّال",         "ar-gulf":"جارٍ"},
    "status.failed":    {"en":"Failed",           "ar":"فشل",           "ar-eg":"وقع",           "ar-gulf":"فشل"},
    "status.pending":   {"en":"Pending",          "ar":"معلّق",         "ar-eg":"واقف",          "ar-gulf":"معلّق"},
    "status.scheduled": {"en":"Scheduled",        "ar":"مجدول",         "ar-eg":"متجدول",        "ar-gulf":"مجدول"},
    "status.active":    {"en":"Active",           "ar":"نشط",           "ar-eg":"شغّال",         "ar-gulf":"نشط"},
    "status.banned":    {"en":"Banned",           "ar":"محظور",         "ar-eg":"موقوف",         "ar-gulf":"محظور"},

    # ── Generate ──────────────────────────────────────────────────
    "gen.title":        {"en":"Generate Content", "ar":"إنشاء محتوى",   "ar-eg":"اعمل محتوى",   "ar-gulf":"إنشاء محتوى"},
    "gen.topic":        {"en":"Topic / Product",  "ar":"الموضوع",       "ar-eg":"الموضوع",       "ar-gulf":"الموضوع"},
    "gen.platforms":    {"en":"Platforms",        "ar":"المنصات",       "ar-eg":"المنصات",       "ar-gulf":"المنصات"},
    "gen.language":     {"en":"Language",         "ar":"اللغة",         "ar-eg":"اللغة",         "ar-gulf":"اللغة"},
    "gen.ideas":        {"en":"Ideas Count",      "ar":"عدد الأفكار",   "ar-eg":"عدد الأفكار",   "ar-gulf":"عدد الأفكار"},
    "gen.submit":       {"en":"✦ Generate",       "ar":"✦ إنشاء",       "ar-eg":"✦ اعمل",        "ar-gulf":"✦ أنشئ"},
    "gen.generating":   {"en":"Generating…",      "ar":"جارٍ الإنشاء…", "ar-eg":"شغّال…",        "ar-gulf":"جارٍ…"},
    "gen.type_static":  {"en":"Static Post",      "ar":"منشور ثابت",    "ar-eg":"بوست ثابت",     "ar-gulf":"منشور ثابت"},
    "gen.type_video":   {"en":"Video",            "ar":"فيديو",         "ar-eg":"فيديو",         "ar-gulf":"فيديو"},
    "gen.competitor_urls":{"en":"Competitor URLs","ar":"روابط المنافسين","ar-eg":"لينكات المنافسين","ar-gulf":"روابط المنافسين"},
    "gen.features":     {"en":"Product Features", "ar":"مميزات المنتج", "ar-eg":"مميزات المنتج", "ar-gulf":"مميزات المنتج"},
    "gen.brand_voice":  {"en":"Brand Voice",      "ar":"صوت العلامة",   "ar-eg":"صوت البراند",   "ar-gulf":"صوت العلامة"},
    "gen.human_review": {"en":"Human review",     "ar":"مراجعة بشرية",  "ar-eg":"راجعها بنفسك",  "ar-gulf":"مراجعة يدوية"},
    "gen.fallback_warn":{"en":"⚠ AI returned limited content — showing fallback ideas.",
                         "ar":"⚠ الذكاء الاصطناعي أرجع محتوى محدود — أفكار احتياطية.",
                         "ar-eg":"⚠ الـ AI مردش حاجة كتير — شايف أفكار بديلة.",
                         "ar-gulf":"⚠ لم يرجع الذكاء الاصطناعي محتوى كافٍ — أفكار بديلة."},

    # ── Dashboard ─────────────────────────────────────────────────
    "dash.welcome":     {"en":"Welcome back",     "ar":"أهلاً بعودتك",  "ar-eg":"أهلاً",         "ar-gulf":"أهلاً بعودتك"},
    "dash.total_gens":  {"en":"Total Generations","ar":"إجمالي الإنشاءات","ar-eg":"كل الإنشاءات","ar-gulf":"إجمالي الإنشاءات"},
    "dash.completed":   {"en":"Completed",        "ar":"مكتملة",        "ar-eg":"خلصت",          "ar-gulf":"مكتملة"},
    "dash.scheduled":   {"en":"Scheduled",        "ar":"مجدولة",        "ar-eg":"متجدولة",       "ar-gulf":"مجدولة"},
    "dash.recent":      {"en":"Recent Generations","ar":"الإنشاءات الأخيرة","ar-eg":"الإنشاءات الأخيرة","ar-gulf":"الإنشاءات الأخيرة"},
    "dash.upcoming":    {"en":"Upcoming",         "ar":"القادم",        "ar-eg":"الجاي",         "ar-gulf":"القادم"},

    # ── History ───────────────────────────────────────────────────
    "hist.title":       {"en":"History",          "ar":"السجل",         "ar-eg":"السجل",         "ar-gulf":"السجل"},
    "hist.topic":       {"en":"Topic",            "ar":"الموضوع",       "ar-eg":"الموضوع",       "ar-gulf":"الموضوع"},
    "hist.type":        {"en":"Type",             "ar":"النوع",         "ar-eg":"النوع",         "ar-gulf":"النوع"},
    "hist.status":      {"en":"Status",           "ar":"الحالة",        "ar-eg":"الحالة",        "ar-gulf":"الحالة"},
    "hist.date":        {"en":"Date",             "ar":"التاريخ",       "ar-eg":"التاريخ",       "ar-gulf":"التاريخ"},
    "hist.no_gens":     {"en":"No generations yet","ar":"لا توجد إنشاءات","ar-eg":"مفيش حاجة لسه","ar-gulf":"لا توجد إنشاءات"},

    # ── Account ───────────────────────────────────────────────────
    "acct.title":       {"en":"Account",          "ar":"الحساب",        "ar-eg":"الحساب",        "ar-gulf":"الحساب"},
    "acct.profile":     {"en":"Profile",          "ar":"الملف الشخصي",  "ar-eg":"البروفايل",     "ar-gulf":"الملف الشخصي"},
    "acct.full_name":   {"en":"Full Name",        "ar":"الاسم الكامل",  "ar-eg":"الاسم",         "ar-gulf":"الاسم الكامل"},
    "acct.email":       {"en":"Email",            "ar":"البريد الإلكتروني","ar-eg":"الإيميل",    "ar-gulf":"البريد الإلكتروني"},
    "acct.password":    {"en":"Password",         "ar":"كلمة المرور",   "ar-eg":"الباسوورد",     "ar-gulf":"كلمة المرور"},
    "acct.save_changes":{"en":"Save Changes",     "ar":"حفظ التغييرات", "ar-eg":"احفظ",          "ar-gulf":"حفظ التغييرات"},
    "acct.api_keys":    {"en":"API Keys",         "ar":"مفاتيح API",    "ar-eg":"مفاتيح الـ API","ar-gulf":"مفاتيح API"},
    "acct.usage":       {"en":"Usage This Month", "ar":"الاستخدام هذا الشهر","ar-eg":"الاستخدام الشهر ده","ar-gulf":"استخدام هذا الشهر"},
    "acct.ui_language": {"en":"Interface Language","ar":"لغة الواجهة",  "ar-eg":"لغة الشاشة",   "ar-gulf":"لغة الواجهة"},

    # ── Admin ─────────────────────────────────────────────────────
    "admin.title":      {"en":"Admin Panel",      "ar":"لوحة المشرف",   "ar-eg":"لوحة الأدمن",  "ar-gulf":"لوحة الإدارة"},
    "admin.users":      {"en":"Users",            "ar":"المستخدمون",    "ar-eg":"اليوزرز",       "ar-gulf":"المستخدمون"},
    "admin.settings":   {"en":"Settings",         "ar":"الإعدادات",     "ar-eg":"السيتنجز",      "ar-gulf":"الإعدادات"},
    "admin.logs":       {"en":"Logs",             "ar":"السجلات",       "ar-eg":"اللوجز",        "ar-gulf":"السجلات"},

    # ── Brand ─────────────────────────────────────────────────────
    "brand.title":      {"en":"Brand Voices",     "ar":"أصوات العلامات","ar-eg":"البراندز",      "ar-gulf":"أصوات العلامات"},
    "brand.new":        {"en":"New Brand",        "ar":"علامة جديدة",   "ar-eg":"براند جديد",    "ar-gulf":"علامة جديدة"},
    "brand.name":       {"en":"Brand Name",       "ar":"اسم العلامة",   "ar-eg":"اسم البراند",   "ar-gulf":"اسم العلامة"},
    "brand.no_brands":  {"en":"No brands yet",    "ar":"لا توجد علامات","ar-eg":"مفيش براندز",   "ar-gulf":"لا توجد علامات"},

    # ── Alerts ────────────────────────────────────────────────────
    "alert.upgrade":    {"en":"Upgrade →",        "ar":"ترقية →",       "ar-eg":"رقّي →",        "ar-gulf":"ترقية →"},

    # ── Insights ──────────────────────────────────────────────────
    "insights.title":   {"en":"Insights",         "ar":"الرؤى",         "ar-eg":"الإنسايتس",     "ar-gulf":"التحليلات"},
    "insights.trend":   {"en":"Trend Intelligence","ar":"ذكاء الترندات","ar-eg":"الترندات",      "ar-gulf":"ذكاء الترندات"},
    "insights.competitor":{"en":"Competitor Analysis","ar":"تحليل المنافسين","ar-eg":"تحليل المنافسين","ar-gulf":"تحليل المنافسين"},

    # ── Pricing ───────────────────────────────────────────────────
    "pricing.title":    {"en":"Upgrade Plan",     "ar":"ترقية الخطة",   "ar-eg":"ترقية الخطة",   "ar-gulf":"ترقية الخطة"},
    "pricing.current":  {"en":"Current Plan",     "ar":"الخطة الحالية", "ar-eg":"خطتك دلوقتي",  "ar-gulf":"الخطة الحالية"},
    "pricing.per_month":{"en":"/mo",              "ar":"/شهر",          "ar-eg":"/شهر",          "ar-gulf":"/شهر"},
}


def t(lang: str, key: str, fallback: str = "") -> str:
    lang_map = TRANSLATIONS.get(key, {})
    if not lang_map:
        return fallback or key
    if lang in lang_map:
        return lang_map[lang]
    if lang.startswith("ar") and "ar" in lang_map:
        return lang_map["ar"]
    return lang_map.get("en", fallback or key)


def is_rtl(lang: str) -> bool:
    return lang in RTL_LANGUAGES


def get_dir(lang: str) -> str:
    return "rtl" if is_rtl(lang) else "ltr"


def get_font(lang: str) -> str:
    if is_rtl(lang):
        return "'Cairo', 'DM Sans', sans-serif"
    return "'DM Sans', sans-serif"


def normalize_lang(lang: str) -> str:
    if not lang:
        return "en"
    mapping = {
        "arabic": "ar", "egyptian arabic": "ar-eg",
        "gulf arabic": "ar-gulf", "english": "en",
        "french": "en", "spanish": "en", "german": "en",
        "fr": "en", "es": "en", "de": "en",
    }
    low = lang.lower().strip()
    if low in mapping:
        return mapping[low]
    return lang if lang in SUPPORTED_LANGUAGES else "en"


def get_language_info(lang: str) -> dict:
    return SUPPORTED_LANGUAGES.get(lang, SUPPORTED_LANGUAGES["en"])
