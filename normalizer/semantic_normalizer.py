from collections.abc import Mapping
import copy
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Pattern

_PATH_RE = re.compile(r"^\$((\.[^.\[\]]+)|(\[\*\]))+$")
_SEGMENT_TOKEN_RE = re.compile(r"\.([^.\[\]]+)|\[\*\]")
_SUPPORTED_ACTIONS = {"DROP", "REGEX_REPLACE", "MAP_STATE"}


class NormalizerConfigError(ValueError):
    """Raised when normalizer configuration is invalid or cannot be loaded."""


@dataclass(frozen=True)
class FieldToken:
    name: str


@dataclass(frozen=True)
class WildcardToken:
    pass


Token = FieldToken | WildcardToken


@dataclass(frozen=True)
class CompiledRule:
    path: str
    tokens: tuple[Token, ...]
    action: str
    pattern: Pattern[str] | None = None
    replacement: str | None = None


def _parse_path(path_str: str) -> tuple[Token, ...]:
    tokens: list[Token] = []
    for match in _SEGMENT_TOKEN_RE.finditer(path_str[1:]):
        field = match.group(1)
        if field is not None:
            tokens.append(FieldToken(name=field))
        else:
            tokens.append(WildcardToken())
    return tuple(tokens)


class SemanticNormalizer:
    def __init__(self, rules: tuple[CompiledRule, ...]) -> None:
        self._rules = rules

    @classmethod
    def from_file(cls, path: str | Path) -> "SemanticNormalizer":
        source_path = Path(path)
        try:
            content = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise NormalizerConfigError(
                f"Failed to read normalizer config from {source_path}: {exc}"
            ) from exc

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise NormalizerConfigError(
                f"Failed to decode normalizer config from {source_path}: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise NormalizerConfigError(
                f"Failed to load normalizer config from {source_path}: root must be an object"
            )

        if "rules" not in data:
            raise NormalizerConfigError(
                f"Failed to load normalizer config from {source_path}: missing 'rules' list"
            )

        raw_rules = data["rules"]
        if not isinstance(raw_rules, list):
            raise NormalizerConfigError(
                f"Failed to load normalizer config from {source_path}: 'rules' must be a list"
            )

        compiled_rules: list[CompiledRule] = []
        for idx, rule in enumerate(raw_rules):
            if not isinstance(rule, dict):
                raise NormalizerConfigError(
                    f"Invalid normalizer rule {idx}: rule must be an object"
                )

            if "path" not in rule:
                raise NormalizerConfigError(
                    f"Invalid normalizer rule {idx}: missing 'path'"
                )

            path_val = rule["path"]
            if not isinstance(path_val, str) or not _PATH_RE.match(path_val):
                target_str = str(path_val) if isinstance(path_val, str) else ""
                suffix = f" ({target_str})" if target_str else ""
                raise NormalizerConfigError(
                    f"Invalid normalizer rule {idx}{suffix}: unsupported path '{path_val}'"
                )

            tokens = _parse_path(path_val)

            if "action" not in rule:
                raise NormalizerConfigError(
                    f"Invalid normalizer rule {idx} ({path_val}): missing 'action'"
                )

            action = rule["action"]
            if action not in _SUPPORTED_ACTIONS:
                raise NormalizerConfigError(
                    f"Invalid normalizer rule {idx} ({path_val}): unsupported action '{action}'"
                )

            pattern: Pattern[str] | None = None
            replacement: str | None = None

            if action == "REGEX_REPLACE":
                if "pattern" not in rule or not isinstance(rule["pattern"], str):
                    raise NormalizerConfigError(
                        f"Invalid normalizer rule {idx} ({path_val}): missing or non-string 'pattern'"
                    )
                if "replacement" not in rule or not isinstance(rule["replacement"], str):
                    raise NormalizerConfigError(
                        f"Invalid normalizer rule {idx} ({path_val}): missing or non-string 'replacement'"
                    )

                try:
                    pattern = re.compile(rule["pattern"])
                except re.error as exc:
                    raise NormalizerConfigError(
                        f"Invalid normalizer rule {idx} ({path_val}): invalid regular expression '{rule['pattern']}': {exc}"
                    ) from exc

                replacement = rule["replacement"]
                try:
                    pattern.sub(replacement, "")
                except re.error as exc:
                    raise NormalizerConfigError(
                        f"Invalid normalizer rule {idx} ({path_val}): invalid replacement '{replacement}': {exc}"
                    ) from exc

            compiled_rules.append(
                CompiledRule(
                    path=path_val,
                    tokens=tokens,
                    action=action,
                    pattern=pattern,
                    replacement=replacement,
                )
            )

        return cls(rules=tuple(compiled_rules))

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    def normalize(
        self,
        payload: Any,
        state_mapping: Mapping[Any, Any] | None = None,
    ) -> Any:
        root = copy.deepcopy(payload)
        for rule in self._rules:
            self._apply_rule(root, rule, 0, state_mapping)
        return root

    def _apply_rule(
        self,
        node: Any,
        rule: CompiledRule,
        token_idx: int,
        state_mapping: Mapping[Any, Any] | None,
    ) -> None:
        tokens = rule.tokens
        token = tokens[token_idx]
        is_leaf = token_idx == len(tokens) - 1

        if isinstance(token, FieldToken):
            if not isinstance(node, dict) or token.name not in node:
                return
            if is_leaf:
                if rule.action == "DROP":
                    del node[token.name]
                else:
                    changed, new_val = self._apply_action(
                        rule, node[token.name], state_mapping
                    )
                    if changed:
                        node[token.name] = new_val
            else:
                self._apply_rule(node[token.name], rule, token_idx + 1, state_mapping)
        elif isinstance(token, WildcardToken):
            if not isinstance(node, list):
                return
            if is_leaf:
                if rule.action == "DROP":
                    for i in range(len(node)):
                        node[i] = None
                else:
                    for i in range(len(node)):
                        changed, new_val = self._apply_action(
                            rule, node[i], state_mapping
                        )
                        if changed:
                            node[i] = new_val
            else:
                for item in node:
                    self._apply_rule(item, rule, token_idx + 1, state_mapping)

    @staticmethod
    def _apply_action(
        rule: CompiledRule,
        val: Any,
        state_mapping: Mapping[Any, Any] | None,
    ) -> tuple[bool, Any]:
        if rule.action == "REGEX_REPLACE":
            if isinstance(val, str) and rule.pattern is not None and rule.replacement is not None:
                return True, rule.pattern.sub(rule.replacement, val)
        elif rule.action == "MAP_STATE":
            if state_mapping is not None:
                try:
                    if val in state_mapping:
                        return True, state_mapping[val]
                except TypeError:
                    pass
        return False, val
