from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AlignOp(StrEnum):
    MATCH = "MATCH"
    INSERT = "INSERT"
    DELETE = "DELETE"
    SUBSTITUTE = "SUBSTITUTE"


@dataclass
class TokenAlign:
    op: AlignOp
    a: str | None
    b: str | None


def tokenize_zh(text: str) -> list[str]:
    """Lightweight Chinese-oriented tokenization: chars + latin words."""
    tokens: list[str] = []
    buf: list[str] = []
    for ch in text.strip():
        if ch.isspace():
            if buf:
                tokens.append("".join(buf))
                buf = []
            continue
        if "a" <= ch.lower() <= "z" or ch.isdigit():
            buf.append(ch)
        else:
            if buf:
                tokens.append("".join(buf))
                buf = []
            if ch.strip():
                tokens.append(ch)
    if buf:
        tokens.append("".join(buf))
    return tokens


def needleman_wunsch(a: list[str], b: list[str], *, match=2, mismatch=-1, gap=-1) -> list[TokenAlign]:
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i * gap
    for j in range(1, m + 1):
        dp[0][j] = j * gap
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            s = match if a[i - 1] == b[j - 1] else mismatch
            dp[i][j] = max(dp[i - 1][j - 1] + s, dp[i - 1][j] + gap, dp[i][j - 1] + gap)
    # traceback
    i, j = n, m
    out: list[TokenAlign] = []
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            s = match if a[i - 1] == b[j - 1] else mismatch
            if dp[i][j] == dp[i - 1][j - 1] + s:
                op = AlignOp.MATCH if a[i - 1] == b[j - 1] else AlignOp.SUBSTITUTE
                out.append(TokenAlign(op, a[i - 1], b[j - 1]))
                i -= 1
                j -= 1
                continue
        if i > 0 and dp[i][j] == dp[i - 1][j] + gap:
            out.append(TokenAlign(AlignOp.DELETE, a[i - 1], None))
            i -= 1
        else:
            out.append(TokenAlign(AlignOp.INSERT, None, b[j - 1] if j > 0 else None))
            j -= 1
    out.reverse()
    return out


@dataclass
class BlockVerdict:
    status: str  # CONFIRMED | DISPUTED | REQUIRES_HUMAN_REVIEW
    text_a: str
    text_b: str
    ops: list[TokenAlign]


def compare_block(text_a: str, text_b: str, *, substitute_limit: int = 2) -> BlockVerdict:
    ta, tb = tokenize_zh(text_a), tokenize_zh(text_b)
    ops = needleman_wunsch(ta, tb)
    subs = sum(1 for o in ops if o.op == AlignOp.SUBSTITUTE)
    ins = sum(1 for o in ops if o.op == AlignOp.INSERT)
    dele = sum(1 for o in ops if o.op == AlignOp.DELETE)
    if text_a.strip() == text_b.strip() or (subs == 0 and abs(ins - dele) <= 1 and ins + dele <= 2):
        status = "CONFIRMED"
    elif subs <= substitute_limit and ins + dele <= 4:
        status = "DISPUTED"
    else:
        status = "DISPUTED"
    return BlockVerdict(status=status, text_a=text_a, text_b=text_b, ops=ops)


def merge_blocks(blocks: list[BlockVerdict]) -> list[dict]:
    out = []
    for i, b in enumerate(blocks):
        out.append(
            {
                "block_index": i,
                "status": b.status,
                "tencent": b.text_a,
                "openai": b.text_b,
                "canonical_candidate": b.text_a if b.status == "CONFIRMED" else None,
            }
        )
    return out
