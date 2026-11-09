"""Language matching data for current and existing user-authored tasks.

Project prose is English; matching vocabulary also accepts existing Portuguese inputs.
"""

EXTRACTION_TERMS = {
    "english": ("exact", "literal", "passage", "extract", "copy", "transcribe", "verbatim"),
    "portuguese": (
        "exato",
        "exata",
        "literal",
        "trecho",
        "extraia",
        "extrair",
        "copie",
        "transcreva",
        "fiel",
    ),
}

INFERENCE_DRIFT_PATTERNS = {
    "english": ("explain why", "justify why", "summarize why", "infer the reason"),
    "portuguese": (
        "explique por que",
        "explique porque",
        "justifique por que",
        "justifique porque",
        "resuma por que",
        "inferir o motivo",
        "inferir a razão",
    ),
}

NO_INVENTION_TERMS = {
    "english": (
        "do not invent",
        "don't invent",
        "do not create information",
        "do not include information that does not exist",
        "use only information present",
        "only information present",
        "only on information present",
        "do not infer missing data",
        "do not assume unmentioned content",
        "base your response only on the text",
    ),
    "portuguese": (
        "não invente",
        "nao invente",
        "não criar",
        "nao criar",
        "não crie informações",
        "nao crie informacoes",
        "não inclua informação que não existe",
        "nao inclua informacao que nao existe",
        "não responda uma informação que não existe",
        "nao responda uma informacao que nao existe",
        "use apenas informações presentes",
        "use apenas informacoes presentes",
        "apenas informações presentes",
        "apenas informacoes presentes",
        "apenas nas informações presentes",
        "apenas nas informacoes presentes",
        "com base apenas nas informações presentes",
        "com base apenas nas informacoes presentes",
        "não deduza dados ausentes",
        "nao deduza dados ausentes",
        "não assuma conteúdo não mencionado",
        "nao assuma conteudo nao mencionado",
        "baseie-se apenas no texto",
        "baseie se apenas no texto",
    ),
}
