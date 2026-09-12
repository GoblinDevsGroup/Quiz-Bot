import enum


class QuizStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class QuizVisibility(str, enum.Enum):
    public = "public"
    private = "private"


class Difficulty(str, enum.Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"
    mixed = "mixed"


class QuestionType(str, enum.Enum):
    multiple_choice = "multiple_choice"
    true_false = "true_false"


class QuizSourceType(str, enum.Enum):
    manual = "manual"
    pdf_ai = "pdf_ai"
    ai_prompt = "ai_prompt"


class GenerationStatus(str, enum.Enum):
    pending = "pending"
    downloading = "downloading"
    extracting = "extracting"
    analyzing = "analyzing"
    generating = "generating"
    validating = "validating"
    completed = "completed"
    failed = "failed"


class ReportReason(str, enum.Enum):
    spam = "spam"
    incorrect_content = "incorrect_content"
    inappropriate = "inappropriate"
    copyright = "copyright"
    other = "other"


class ReportStatus(str, enum.Enum):
    open = "open"
    reviewed = "reviewed"
    dismissed = "dismissed"


class AdminRole(str, enum.Enum):
    super_admin = "super_admin"
    admin = "admin"
    moderator = "moderator"


class Locale(str, enum.Enum):
    uz = "uz"
    ru = "ru"
    en = "en"
