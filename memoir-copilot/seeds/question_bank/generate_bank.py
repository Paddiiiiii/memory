"""Generate seeds/question_bank/question_bank_v1.json"""
from __future__ import annotations

import json
from pathlib import Path

TOPICS = [
    ("家庭与祖辈", ["祖父母", "父母", "兄弟姐妹", "家族故事"]),
    ("童年", ["游戏", "邻里", "节日", "童年住所"]),
    ("教育", ["入学", "老师", "同学", "辍学或升学"]),
    ("青少年", ["志向", "友谊", "时代氛围"]),
    ("工作", ["第一份工作", "同事", "收入", "职业转折"]),
    ("婚恋", ["相识", "恋爱", "结婚", "夫妻生活"]),
    ("子女", ["生育", "养育", "亲子关系"]),
    ("居住与迁移", ["搬家", "进城", "回乡"]),
    ("重大转折", ["社会运动", "政策变化", "意外", "转机"]),
    ("时代生活", ["物资", "交通", "媒体", "日常"]),
    ("重要人物", ["师傅", "领导", "朋友", "贵人"]),
    ("老年与退休", ["退休", "晚年生活", "健康"]),
    ("人生感悟", ["后悔", "骄傲", "想对后人说"]),
    (
        "人生第一次",
        [
            "FIRST_SCHOOL",
            "FIRST_JOB",
            "FIRST_SALARY",
            "FIRST_LEAVE_HOME",
            "FIRST_TRIP_ALONE",
            "FIRST_LOVE",
            "FIRST_MARRIAGE",
            "FIRST_PARENT",
            "FIRST_HOME",
            "FIRST_MAJOR_PURCHASE",
            "FIRST_SUCCESS",
            "FIRST_FAILURE",
            "FIRST_LOSS",
            "FIRST_RETIREMENT",
            "FIRST_GRANDPARENT",
        ],
    ),
]

EXTRA = [
    "第一次领工资那天怎么花的？",
    "离开家乡那天谁来送您？",
    "您母亲最让您难忘的一件小事？",
    "工作里遇到过最大的委屈是什么？",
    "有没有差点改变人生轨迹的选择？",
    "邻居里谁对您影响最大？",
    "困难时期家里怎么过的？",
    "第一次进城是什么感觉？",
    "孩子出生那天您在做什么？",
    "退休第一天您做了什么？",
]


def main() -> None:
    bank: dict = {"version": "question_bank_v1", "topics": [], "questions": []}
    qid = 1
    for tname, children in TOPICS:
        tid = f"topic_{len(bank['topics']) + 1:03d}"
        bank["topics"].append({"id": tid, "name": tname, "parent_id": None})
        child_ids = []
        for c in children:
            cid = f"topic_{len(bank['topics']) + 1:03d}"
            bank["topics"].append({"id": cid, "name": c, "parent_id": tid})
            child_ids.append((cid, c))
        for cid, c in child_ids:
            texts = [
                f"能聊聊{c}吗？",
                f"关于{c}，您印象最深的一件事是什么？",
            ]
            if tname == "人生第一次":
                texts = [f"还记得您的{c}吗？可以讲讲当时的情形吗？"]
            for text in texts:
                bank["questions"].append(
                    {
                        "id": f"q_{qid:03d}",
                        "text": text,
                        "primary_topic": cid,
                        "tags": [tname, c],
                        "importance": round(0.55 + (qid % 5) * 0.08, 2),
                        "required_slots": ["时间", "地点", "人物", "经过", "感受"],
                        "covered_slots": [],
                        "missing_slots": ["时间", "地点", "人物", "经过", "感受"],
                        "coverage": 0.0,
                        "status": "open",
                        "first_experience_bonus": tname == "人生第一次",
                        "first_type": c if tname == "人生第一次" else None,
                    }
                )
                qid += 1

    work = next(t["id"] for t in bank["topics"] if t["name"] == "工作" and t["parent_id"] is None)
    for text in EXTRA:
        bank["questions"].append(
            {
                "id": f"q_{qid:03d}",
                "text": text,
                "primary_topic": work,
                "tags": ["补充"],
                "importance": 0.7,
                "required_slots": ["经过", "感受"],
                "covered_slots": [],
                "missing_slots": ["经过", "感受"],
                "coverage": 0.0,
                "status": "open",
                "first_experience_bonus": False,
                "first_type": None,
            }
        )
        qid += 1

    out = Path(__file__).resolve().parents[1] / "question_bank" / "question_bank_v1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out} questions={len(bank['questions'])} topics={len(bank['topics'])}")


if __name__ == "__main__":
    main()
