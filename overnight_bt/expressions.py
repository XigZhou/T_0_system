from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass
from typing import Any, Callable

from .sector_features import SECTOR_CATEGORICAL_COLUMNS, SECTOR_NUMERIC_COLUMNS


_NUMERIC_FIELDS = {
    "open",
    "high",
    "low",
    "close",
    "pct_chg",
    "vol",
    "vol5",
    "vol10",
    "vr",
    "amount",
    "amount5",
    "amount10",
    "amp",
    "amp5",
    "listed_days",
    "total_mv_snapshot",
    "turnover_rate_snapshot",
    "ret1",
    "ret2",
    "ret3",
    "ma5",
    "ma10",
    "ma20",
    "bias_ma5",
    "bias_ma10",
    "close_to_up_limit",
    "high_to_up_limit",
    "close_pos_in_bar",
    "body_pct",
    "upper_shadow_pct",
    "lower_shadow_pct",
    "vol_ratio_5",
    "ret_accel_3",
    "vol_ratio_3",
    "amount_ratio_3",
    "body_pct_3avg",
    "close_to_up_limit_3max",
    "days_held",
    "holding_return",
    "best_return_since_entry",
    "drawdown_from_peak",
    "industry_m20",
    "industry_m60",
    "industry_rank_m20",
    "industry_rank_m60",
    "industry_up_ratio",
    "industry_strong_ratio",
    "industry_amount",
    "industry_amount20",
    "industry_amount_ratio",
    "industry_stock_count",
    "industry_valid_m20_count",
    "stock_vs_industry_m20",
    "stock_vs_industry_m60",
}
_NUMERIC_FIELDS.update({f"m{n}" for n in [5, 10, 20, 30, 60, 120]})
_NUMERIC_FIELDS.update(SECTOR_NUMERIC_COLUMNS)
_CATEGORICAL_FIELDS = {
    "board",
    "market",
    "industry",
}
_CATEGORICAL_FIELDS.update(SECTOR_CATEGORICAL_COLUMNS)
_AVG_FIELD_RE = re.compile(r"^avg(?:5|10)m\d+$")
_ROLLING_HL_RE = re.compile(r"^(?:high|low)_\d+$")
_MARKET_PREFIX_RE = re.compile(r"^(sh|hs300|cyb)_(.+)$")
_OPERAND_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?$")
_NUM_RE = re.compile(r"^[-+]?\d*\.?\d+$")
_SCALED_FIELD_RE = re.compile(r"^([-+]?\d*\.?\d+)\*?([A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?)$")
_FIELD_TIMES_NUM_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?)\*([-+]?\d*\.?\d+)$")
_CHAINED_RE = re.compile(
    r"^\s*([-+]?\d*\.?\d+)\s*(<=|<)\s*([A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?)\s*(<=|<)\s*([-+]?\d*\.?\d+)\s*$"
)
_OFFSET_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\[(\d+)\]")


@dataclass(frozen=True)
class Condition:
    field: str
    field_offset: int
    op: str
    threshold: float | str | None
    rhs_field: str | None
    rhs_field_offset: int
    rhs_multiplier: float
    is_text: bool = False


_OPS: dict[str, Callable[[float, float], bool]] = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def _is_supported_numeric_field(name: str) -> bool:
    if name in _NUMERIC_FIELDS or bool(_AVG_FIELD_RE.match(name)) or bool(_ROLLING_HL_RE.match(name)):
        return True
    market_match = _MARKET_PREFIX_RE.match(name)
    if not market_match:
        return False
    suffix = market_match.group(2)
    return suffix in _NUMERIC_FIELDS or bool(_AVG_FIELD_RE.match(suffix)) or bool(_ROLLING_HL_RE.match(suffix))


def _is_supported_condition_field(name: str) -> bool:
    return _is_supported_numeric_field(name) or name in _CATEGORICAL_FIELDS


def _is_categorical_field(name: str) -> bool:
    return name in _CATEGORICAL_FIELDS


def _normalize_operator_chars(expr: str) -> str:
    return expr.replace("≤", "<=").replace("≥", ">=")


def _split_binary_token(part: str) -> tuple[str, str, str]:
    compact = part.replace(" ", "")
    for op in (">=", "<=", "==", "!=", "=", ">", "<"):
        idx = compact.find(op)
        if idx <= 0:
            continue
        lhs = compact[:idx]
        rhs = compact[idx + len(op) :]
        if rhs:
            return lhs, op, rhs
    raise ValueError(f"invalid condition token: {part}")


def _parse_operand(token: str, *, allow_categorical: bool = False) -> tuple[str, int]:
    match = _OPERAND_RE.match(token.strip().lower())
    if not match:
        raise ValueError(f"invalid field token: {token}")
    field = match.group(1)
    offset = int(match.group(2) or 0)
    supported = _is_supported_condition_field(field) if allow_categorical else _is_supported_numeric_field(field)
    if not supported:
        raise ValueError(f"unsupported field: {field}")
    if _is_categorical_field(field) and offset > 0:
        raise ValueError(f"categorical field does not support lag: {field}")
    return field, offset


def _parse_single_condition_token(part: str) -> list[Condition]:
    part = _normalize_operator_chars(part.strip())
    chain_match = _CHAINED_RE.match(part)
    if chain_match:
        lower = float(chain_match.group(1))
        left_op = chain_match.group(2)
        mid_operand = chain_match.group(3)
        right_op = chain_match.group(4)
        upper = float(chain_match.group(5))
        field, field_offset = _parse_operand(mid_operand, allow_categorical=False)
        lower_op = ">=" if left_op == "<=" else ">"
        upper_op = "<=" if right_op == "<=" else "<"
        return [
            Condition(field, field_offset, lower_op, lower, None, 0, 1.0),
            Condition(field, field_offset, upper_op, upper, None, 0, 1.0),
        ]

    lhs_raw, op, rhs_raw = _split_binary_token(part)
    field, field_offset = _parse_operand(lhs_raw, allow_categorical=True)
    if op == "=":
        op = "=="
    rhs_field: str | None = None
    rhs_field_offset = 0
    threshold: float | str | None = None
    rhs_multiplier = 1.0

    if _is_categorical_field(field):
        if op not in ("==", "!="):
            raise ValueError(f"categorical field only supports == or != : {field}")
        text_value = rhs_raw.strip()
        if len(text_value) >= 2 and text_value[0] == text_value[-1] and text_value[0] in {"'", '"'}:
            text_value = text_value[1:-1]
        if not text_value:
            raise ValueError(f"categorical field requires text value: {field}")
        return [Condition(field, field_offset, op, text_value, None, 0, 1.0, is_text=True)]

    if _NUM_RE.match(rhs_raw):
        threshold = float(rhs_raw)
    else:
        rhs_compact = rhs_raw.replace(" ", "")
        scaled_match = _SCALED_FIELD_RE.match(rhs_compact)
        field_scale_match = _FIELD_TIMES_NUM_RE.match(rhs_compact)
        rhs_operand = rhs_raw
        if scaled_match:
            rhs_multiplier = float(scaled_match.group(1))
            rhs_operand = scaled_match.group(2)
        elif field_scale_match:
            rhs_operand = field_scale_match.group(1)
            rhs_multiplier = float(field_scale_match.group(2))
        rhs_field, rhs_field_offset = _parse_operand(rhs_operand, allow_categorical=False)

    return [Condition(field, field_offset, op, threshold, rhs_field, rhs_field_offset, rhs_multiplier)]


def _format_field_with_offset(field: str, offset: int) -> str:
    return field if offset <= 0 else f"{field}[{offset}]"


def _read_value(row: dict[str, Any], field: str, offset: int) -> float | None:
    key = _format_field_with_offset(field, offset)
    raw = row.get(key, row.get(field) if offset == 0 else None)

    if field == "vr":
        try:
            if raw is not None:
                return float(raw)
        except Exception:
            return None
        vol_raw = row.get(_format_field_with_offset("vol", offset))
        vol5_raw = row.get(_format_field_with_offset("vol5", offset))
        try:
            if vol_raw is None or vol5_raw is None:
                return None
            vol_f = float(vol_raw)
            vol5_f = float(vol5_raw)
            if vol5_f == 0:
                return None
            return vol_f / vol5_f
        except Exception:
            return None

    try:
        if raw is None:
            return None
        return float(raw)
    except Exception:
        return None


def _read_text_value(row: dict[str, Any], field: str, offset: int) -> str | None:
    key = _format_field_with_offset(field, offset)
    raw = row.get(key, row.get(field) if offset == 0 else None)
    if raw is None:
        return None
    text = str(raw).strip()
    return text if text else None


def max_required_offset(conditions: list[Condition]) -> int:
    return max((max(c.field_offset, c.rhs_field_offset) for c in conditions), default=0)


def parse_condition_expr(expr: str) -> list[Condition]:
    if expr is None:
        raise ValueError("condition expression is empty")
    parts = [part.strip() for part in expr.split(",") if part.strip()]
    if not parts:
        raise ValueError("condition expression is empty")
    out: list[Condition] = []
    for part in parts:
        out.extend(_parse_single_condition_token(part))
    return out


def evaluate_conditions(row: dict[str, Any], conditions: list[Condition]) -> tuple[bool, str]:
    for cond in conditions:
        lhs_name = _format_field_with_offset(cond.field, cond.field_offset)
        if cond.is_text:
            lhs_text = _read_text_value(row, cond.field, cond.field_offset)
            if lhs_text is None:
                return False, f"{lhs_name} missing"
            rhs_text = str(cond.threshold).strip()
            if cond.op == "==" and lhs_text != rhs_text:
                return False, f"{lhs_name} == {rhs_text} not satisfied"
            if cond.op == "!=" and lhs_text == rhs_text:
                return False, f"{lhs_name} != {rhs_text} not satisfied"
            continue

        lhs_f = _read_value(row, cond.field, cond.field_offset)
        if lhs_f is None:
            return False, f"{lhs_name} missing"

        if cond.rhs_field is not None:
            rhs_name = _format_field_with_offset(cond.rhs_field, cond.rhs_field_offset)
            rhs_f = _read_value(row, cond.rhs_field, cond.rhs_field_offset)
            if rhs_f is None:
                return False, f"{rhs_name} missing"
            rhs_value = rhs_f * cond.rhs_multiplier
        else:
            rhs_value = float(cond.threshold)

        if not _OPS[cond.op](lhs_f, rhs_value):
            return False, f"{lhs_name} {cond.op} {rhs_value} not satisfied"
    return True, "satisfied"


class ScoreExpressionError(ValueError):
    pass


def _preprocess_score_expression(expr: str) -> str:
    return _OFFSET_TOKEN_RE.sub(r'lag("\1", \2)', expr.strip())


class _ScoreValidator(ast.NodeVisitor):
    _allowed_binops = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod)
    _allowed_unary = (ast.UAdd, ast.USub)
    _allowed_calls = {"abs", "min", "max", "lag"}

    def visit(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return self.visit(node.body)
        return super().visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if not isinstance(node.op, self._allowed_binops):
            raise ScoreExpressionError("unsupported binary operator")
        self.visit(node.left)
        self.visit(node.right)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        if not isinstance(node.op, self._allowed_unary):
            raise ScoreExpressionError("unsupported unary operator")
        self.visit(node.operand)

    def visit_Call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Name) or node.func.id not in self._allowed_calls:
            raise ScoreExpressionError("unsupported function")
        for arg in node.args:
            self.visit(arg)

    def visit_Name(self, node: ast.Name) -> None:
        if not _is_supported_numeric_field(node.id.lower()):
            raise ScoreExpressionError(f"unsupported field: {node.id}")

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, (int, float, str)):
            raise ScoreExpressionError("unsupported constant")

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(
            node,
            (
                ast.Load,
                ast.Expr,
                ast.Tuple,
                ast.List,
            ),
        ):
            super().generic_visit(node)
            return
        if isinstance(
            node,
            (
                ast.Expression,
                ast.BinOp,
                ast.UnaryOp,
                ast.Call,
                ast.Name,
                ast.Constant,
            ),
        ):
            super().generic_visit(node)
            return
        raise ScoreExpressionError(f"unsupported syntax: {type(node).__name__}")


def compile_score_expression(expr: str) -> tuple[ast.AST, str]:
    if expr is None or not str(expr).strip():
        raise ScoreExpressionError("score expression is empty")
    prepared = _preprocess_score_expression(str(expr))
    try:
        tree = ast.parse(prepared, mode="eval")
    except SyntaxError as exc:
        raise ScoreExpressionError(f"invalid score expression: {exc}") from exc
    _ScoreValidator().visit(tree)
    return tree, prepared


def _safe_lag(row: dict[str, Any], field: str, offset: int) -> float:
    value = _read_value(row, field.lower(), int(offset))
    if value is None:
        return math.nan
    return value


def evaluate_score_expression(row: dict[str, Any], expr: str | ast.AST) -> float:
    tree = expr if isinstance(expr, ast.AST) else compile_score_expression(expr)[0]
    compiled = compile(tree, "<score_expression>", "eval")
    names: dict[str, Any] = {
        key: _read_value(row, key, 0) if _is_supported_numeric_field(key) else row.get(key)
        for key in {str(k).lower() for k in row.keys() if "[" not in str(k)}
    }
    names.update(
        {
            "abs": abs,
            "min": min,
            "max": max,
            "lag": lambda field, offset: _safe_lag(row, str(field), int(offset)),
        }
    )
    try:
        value = eval(compiled, {"__builtins__": {}}, names)
    except Exception as exc:
        raise ScoreExpressionError(f"failed to evaluate score expression: {exc}") from exc
    try:
        return float(value)
    except Exception as exc:
        raise ScoreExpressionError(f"score expression did not produce a number: {value}") from exc
