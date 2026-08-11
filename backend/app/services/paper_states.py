"""论文投稿状态机。合法转移表之外的变更一律拒绝，前后端共用此定义。"""

TRANSITIONS: dict[str, list[str]] = {
    "Draft": ["Submitted"],                              # 草稿 -> 已投稿
    "Submitted": ["Under Review", "Rejected"],           # 已投稿 -> 审稿中/已拒稿
    "Under Review": ["Revision", "Accepted", "Rejected"],
    "Revision": ["Resubmitted", "Rejected"],             # 修改中 -> 已重投/已拒稿
    "Resubmitted": ["Under Review", "Accepted", "Rejected"],
    "Accepted": ["Published"],                           # 已接收 -> 已发表
    "Rejected": ["Submitted"],                           # 被拒后可重投复活
    "Published": [],                                     # 终态
}


def next_statuses(current: str) -> list[str]:
    return TRANSITIONS.get(current, [])


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, [])
