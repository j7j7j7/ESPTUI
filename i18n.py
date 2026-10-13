"""Internationalization (i18n) module for ESPTUI."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class SafeDict(dict):
    """Dictionary that returns the unformatted placeholder when a key is missing."""
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def get_search_directories() -> List[Path]:
    """Returns candidate directories containing language files in priority order."""
    dirs: List[Path] = [
        Path(__file__).resolve().parent / "config" / "lang",
        Path.cwd() / "config" / "lang",
        Path.home() / ".esptui" / "lang",
    ]
    seen = set()
    result = []
    for d in dirs:
        resolved = d.resolve()
        if resolved not in seen:
            seen.add(resolved)
            if resolved.is_dir():
                result.append(resolved)
    return result


class I18n:
    """Manages language detection, translation loading, and string interpolation."""

    def __init__(self, default_lang: str = "en", lang_dirs: Optional[List[Path]] = None):
        self.lang_dirs = lang_dirs or get_search_directories()
        self.available_languages: Dict[str, Dict[str, Any]] = {}
        self.translations: Dict[str, Dict[str, Any]] = {}
        self.current_lang = default_lang
        self.scan_languages()
        
        # Load English as baseline fallback
        if "en" in self.available_languages:
            self.load_language("en")
        
        # Ensure default language is loaded
        if self.current_lang in self.available_languages:
            self.load_language(self.current_lang)
        elif "en" in self.available_languages:
            self.current_lang = "en"
        elif self.available_languages:
            self.current_lang = next(iter(self.available_languages))
            self.load_language(self.current_lang)

    def scan_languages(self) -> None:
        """Discovers all JSON translation files across search directories."""
        self.available_languages.clear()
        for directory in self.lang_dirs:
            if not directory.is_dir():
                continue
            for file_path in sorted(directory.glob("*.json")):
                code = file_path.stem.lower()
                name = code.upper()
                try:
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        meta = data.get("_meta", {})
                        if isinstance(meta, dict) and "name" in meta:
                            name = meta["name"]
                except Exception:
                    pass
                if code not in self.available_languages:
                    self.available_languages[code] = {
                        "code": code,
                        "name": name,
                        "path": file_path,
                    }

    def load_language(self, lang_code: str) -> None:
        """Loads and caches translation dictionary for a language code."""
        if lang_code in self.translations:
            return
        meta = self.available_languages.get(lang_code)
        if not meta:
            return
        path: Path = meta["path"]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.translations[lang_code] = data
        except Exception:
            self.translations[lang_code] = {}

    def set_language(self, lang_code: str) -> bool:
        """Switches current language if available."""
        lang_code = lang_code.lower()
        if lang_code in self.available_languages:
            self.load_language(lang_code)
            self.current_lang = lang_code
            return True
        return False

    @property
    def has_multiple_languages(self) -> bool:
        """Returns True if more than 1 language file is available."""
        return len(self.available_languages) > 1

    def get_language_options(self) -> List[Tuple[str, str]]:
        """Returns list of (display_name, code) tuples for UI selector."""
        return [
            (info["name"], code)
            for code, info in sorted(self.available_languages.items())
        ]

    def _resolve_key(self, data: Dict[str, Any], key_path: str) -> Optional[str]:
        keys = key_path.split(".")
        current: Any = data
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        return current if isinstance(current, str) else None

    def t(self, key_path: str, default: Optional[str] = None, **kwargs: Any) -> str:
        """Translates a dotted key with fallback and string interpolation."""
        val = None
        # Try active language
        if self.current_lang in self.translations:
            val = self._resolve_key(self.translations[self.current_lang], key_path)

        # Fallback to English
        if val is None and self.current_lang != "en" and "en" in self.translations:
            val = self._resolve_key(self.translations["en"], key_path)

        # Fallback to provided default or last segment of key
        if val is None:
            val = default if default is not None else key_path

        if kwargs:
            try:
                return val.format_map(SafeDict(**kwargs))
            except Exception:
                return val
        return val


# Global default instance
_default_i18n: Optional[I18n] = None


def get_i18n(default_lang: str = "en") -> I18n:
    global _default_i18n
    if _default_i18n is None:
        _default_i18n = I18n(default_lang=default_lang)
    elif default_lang and _default_i18n.current_lang != default_lang:
        _default_i18n.set_language(default_lang)
    return _default_i18n
