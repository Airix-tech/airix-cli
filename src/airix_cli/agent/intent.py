# src/airix_cli/agent/intent.py
import re
import unicodedata

# Verbos que indican que el usuario quiere tocar archivos. Se comparan sobre el
# texto sin tildes (ver _normalize), por eso "corrígelo" o "añade" aparecen aquí
# como "corrigelo" y "anade". Solo formas imperativas/infinitivas o de
# subjuntivo: sustantivos como "cambios" o "mejoras" no deben activar el modo
# de cambios ("¿qué mejoras harías?" es una consulta).
_CHANGE_VERBS = re.compile(
    r"""\b(?:
        modific(?:a|ar|arlo|arla|alo|ala|ue|ues|uen)
      | cambi(?:a|ar|arlo|arla|alo|ala|e|es|en)
      | corrig(?:e|elo|ela|en|es) | correg(?:ir|irlo|irla) | corrij(?:a|as|an)
      | arregl(?:a|ar|arlo|arla|alo|ala|e|es|en)
      | agreg(?:a|ar|alo|ala|ale|arle|ue|ues|uen)
      | anad(?:e|ir|elo|ela|ele|irle|a|as|an)
      | refactoriz(?:a|ar|arlo|arla|alo|ala) | refactoric(?:e|es|en)
      | implement(?:a|ar|arlo|arla|alo|ala|e|es|en)
      | cre(?:a|ar|arlo|arla|alo|ala)
      | gener(?:a|ar|arlo|arla|alo|ala)
      | escrib(?:e|ir|irlo|irla|elo|ela|as|an)
      | elimin(?:a|ar|arlo|arla|alo|ala|e|es|en)
      | borr(?:a|ar|arlo|arla|alo|ala|es|en)
      | quit(?:a|ar|arlo|arla|alo|ala|es|en)
      | actualiz(?:a|ar|arlo|arla|alo|ala) | actualic(?:e|es|en)
      | reemplaz(?:a|ar|arlo|arla|alo|ala) | reemplac(?:e|es|en)
      | renombr(?:a|ar|arlo|arla|alo|ala|e|es|en)
      | optimiz(?:a|ar|arlo|arla|alo|ala) | optimic(?:e|es|en)
      | mejor(?:ar|arlo|arla|alo|ala)
      | aplic(?:a|ar|arlo|arla|alo|ala) | apliqu(?:e|es|en)
      | fix | modify | change | refactor | implement | create | write | add
      | remove | delete | update | rename | apply
    )\b""",
    re.VERBOSE,
)
_NEGATIONS = {"no", "sin", "nunca", "not", "dont", "don't", "without", "never"}
_QUESTION_WORDS = {"que", "como", "cual", "cuales", "donde", "cuando", "what", "how", "which", "where", "why", "when"}
_FILE_NAME = re.compile(r"\S+\.\w+")
_CLAUSE_SEPARATORS = re.compile(r"[.,;:!?¿¡\n]")


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def is_change_request(instruction: str) -> bool:
    """
    Decide si la instrucción pide modificar archivos (propuestas en `.tmp/`) o
    si es una consulta (analizar, revisar, explicar) que se responde en el CLI.

    Se resuelve aquí y no en el prompt porque los modelos locales pequeños
    (p. ej. qwen2.5-coder:7b) rellenan `files` aunque solo se les pida revisar
    un archivo. Ante la duda gana la consulta: responder en texto nunca escribe
    en disco, y el usuario siempre puede pedir el cambio explícitamente.
    """
    # Los nombres de archivo no cuentan: "update_config.py" no es un "update".
    text = _FILE_NAME.sub(" ", _normalize(instruction))
    is_question = "?" in text
    for match in _CHANGE_VERBS.finditer(text):
        clause = _CLAUSE_SEPARATORS.split(text[: match.start()])[-1]
        words = re.findall(r"[a-z']+", clause)
        # "analízalo sin modificar nada", "no cambies el archivo"
        if any(word in _NEGATIONS for word in words[-3:]):
            continue
        # "¿qué genera esta función?" pregunta por el código, no pide generarlo.
        if is_question and words and words[0] in _QUESTION_WORDS:
            continue
        return True
    return False
