"""常用目标期刊预设（可编辑，启动时若库空则初始化）。"""

JOURNAL_PRESETS = [
    # (名称, 分区, IF, 审稿周期周, 备注)
    ("Nature", "Q1", "50.5", 8, "综合顶刊"),
    ("Nature Communications", "Q1", "16.6", 6, "开放获取"),
    ("Science Advances", "Q1", "13.6", 6, "开放获取"),
    ("IEEE TPAMI", "Q1", "20.8", 6, "模式识别/计算机视觉"),
    ("NeurIPS", "Q1", "—", 4, "机器学习顶会（口头/海报）"),
    ("ICML", "Q1", "—", 4, "机器学习顶会"),
    ("ICLR", "Q1", "—", 4, "表征学习顶会"),
    ("AAAI", "Q1", "—", 4, "人工智能顶会"),
    ("CVPR", "Q1", "—", 4, "计算机视觉顶会"),
    ("ACL", "Q1", "—", 4, "自然语言处理顶会"),
    ("Cell", "Q1", "64.5", 8, "生物医学顶刊"),
    ("Nature Methods", "Q1", "48.0", 8, "方法学"),
    ("Bioinformatics", "Q2", "5.8", 6, "生物信息学"),
    ("Nucleic Acids Research", "Q1", "14.9", 6, "分子生物学/数据库"),
    ("Genome Biology", "Q1", "12.3", 6, "基因组学"),
    ("Physical Review Letters", "Q1", "8.6", 4, "物理快报"),
    ("IEEE TIP", "Q1", "10.6", 6, "图像处理"),
    ("Pattern Recognition", "Q1", "8.0", 5, "模式识别"),
    ("Artificial Intelligence Review", "Q1", "12.0", 6, "AI 综述"),
    ("Expert Systems with Applications", "Q1", "8.5", 5, "应用系统"),
]
