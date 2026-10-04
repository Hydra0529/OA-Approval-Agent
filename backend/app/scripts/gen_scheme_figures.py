"""Figures that match the running codebase (not a four-layer product architecture)."""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib import font_manager

OUT = Path(__file__).resolve().parents[3] / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

for p in [
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
]:
    if p.exists():
        font_manager.fontManager.addfont(str(p))
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
        break
plt.rcParams["axes.unicode_minus"] = False

NAVY = "#1F4E79"
TEAL = "#2E75B6"
GOLD = "#C45911"
GREEN = "#548235"
GRAY = "#595959"


def _box(ax, x, y, w, h, text, fc=TEAL, fs=10):
    p = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.1,
        edgecolor=NAVY,
        facecolor=fc,
        alpha=0.95,
    )
    ax.add_patch(p)
    ax.text(
        x + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        color="white",
        fontsize=fs,
        fontweight="bold",
        wrap=True,
    )


def fig_system():
    fig, ax = plt.subplots(figsize=(11.2, 6.4), dpi=160)
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.text(6, 6.6, "本系统实际构成（对应仓库目录）", ha="center", fontsize=14, color=NAVY, fontweight="bold")

    _box(ax, 0.4, 5.2, 5.2, 1.05, "前端  frontend/\nReact + Vite  项目群清单 / 日历 / BPMN / 申报窗口", NAVY, 10)
    _box(ax, 6.4, 5.2, 5.2, 1.05, "后端  backend/app\nFastAPI  /api/*  本地 8000 端口", TEAL, 10)

    _box(ax, 0.4, 3.55, 2.5, 1.25, "制度学习\norchestrator\ndept_learner", GREEN, 9)
    _box(ax, 3.15, 3.55, 2.5, 1.25, "申报生成\nintake\nweb_lookup", GOLD, 9)
    _box(ax, 5.9, 3.55, 2.5, 1.25, "推演监控\nmonitor / org\nstall", TEAL, 9)
    _box(ax, 8.65, 3.55, 2.95, 1.25, "展示\nbpmn / report\n词法 RAG", NAVY, 9)

    _box(ax, 0.4, 1.7, 11.2, 1.4,
         "数据目录  data/\npolicies 制度PDF   templates 四类底稿YAML   cases 单据JSON\n"
         "generated 按单路径   org 部门并行数   index/policy_index.json 词法索引",
         "#3D5A80", 10)

    _box(ax, 0.4, 0.25, 11.2, 1.15,
         "可选大模型：OpenAI 兼容接口（当前可配 qwen-max）\n用于制度抽取、申报解析、法务所需材料识别、分析报告；未配置密钥时改用规则降级",
         GRAY, 9)

    fig.tight_layout()
    fig.savefig(OUT / "system_real.png", bbox_inches="tight", facecolor="white")
    plt.close()


def fig_submit_flow():
    fig, ax = plt.subplots(figsize=(11.2, 3.6), dpi=160)
    ax.set_xlim(0, 12.2)
    ax.set_ylim(0, 3.4)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.text(6.1, 3.1, "提交申报后的实际处理顺序", ha="center", fontsize=13, color=NAVY, fontweight="bold")
    steps = [
        (0.25, "读取 PDF/TXT\n抽字段与受控作业"),
        (2.55, "词法检索\n相关制度片段"),
        (4.85, "生成本单路径\n(立项按金额)"),
        (7.15, "合规审查\n缺件则卡住"),
        (9.45, "写入 cases/\n刷新清单日历"),
    ]
    for i, (x, t) in enumerate(steps):
        _box(ax, x, 0.7, 2.15, 1.7, t, TEAL if i % 2 == 0 else GOLD, 9)
        if i < len(steps) - 1:
            ax.annotate(
                "",
                xy=(x + 2.25, 1.55),
                xytext=(x + 2.15, 1.55),
                arrowprops=dict(arrowstyle="->", color=GRAY, lw=1.4),
            )
    fig.tight_layout()
    fig.savefig(OUT / "submit_flow.png", bbox_inches="tight", facecolor="white")
    plt.close()


def fig_architecture():
    fig, ax = plt.subplots(figsize=(11.2, 6.8), dpi=160)
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7.4)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.text(6, 7.1, "系统总体架构", ha="center", fontsize=14, color=NAVY, fontweight="bold")

    _box(ax, 0.4, 5.85, 11.2, 0.95, "表现层    React + Vite    项目群清单 / 部门日历 / 申报与制度窗口 / BPMN 与报告", NAVY, 10)
    _box(
        ax,
        0.4,
        3.55,
        11.2,
        2.0,
        "应用服务层    FastAPI\n制度学习    申报受理与路径生成    合规审查    监控推演    报告与流程图生成",
        TEAL,
        10,
    )
    _box(
        ax,
        0.4,
        1.7,
        11.2,
        1.55,
        "数据层    本地文件\n制度 PDF    流程底稿 YAML    单据 JSON    词法索引    部门与并行容量",
        GREEN,
        10,
    )
    _box(ax, 0.4, 0.25, 5.4, 1.15, "外部：OpenAI 兼容大模型接口\n（可选，未配置则规则降级）", GRAY, 9)
    _box(ax, 6.2, 0.25, 5.4, 1.15, "外部：公开网页检索\n（合规说明补充，失败用本地条目）", GOLD, 9)

    fig.tight_layout()
    fig.savefig(OUT / "architecture.png", bbox_inches="tight", facecolor="white")
    plt.close()


def fig_division():
    fig, ax = plt.subplots(figsize=(11.2, 4.2), dpi=160)
    ax.set_xlim(0, 12.2)
    ax.set_ylim(0, 4.4)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.text(6.1, 4.05, "系统划分", ha="center", fontsize=14, color=NAVY, fontweight="bold")
    items = [
        (0.25, "制度学习\n分系统"),
        (2.65, "申报与路径\n生成分系统"),
        (5.05, "合规审查\n分系统"),
        (7.45, "监控推演\n分系统"),
        (9.85, "展示交互\n分系统"),
    ]
    colors = [GREEN, GOLD, TEAL, NAVY, GRAY]
    for (x, t), c in zip(items, colors):
        _box(ax, x, 0.55, 2.15, 3.1, t, c, 11)
    fig.tight_layout()
    fig.savefig(OUT / "division.png", bbox_inches="tight", facecolor="white")
    plt.close()


def fig_learn_flow():
    fig, ax = plt.subplots(figsize=(11.2, 3.4), dpi=160)
    ax.set_xlim(0, 12.2)
    ax.set_ylim(0, 3.2)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.text(6.1, 2.9, "制度学习主流程", ha="center", fontsize=13, color=NAVY, fontweight="bold")
    steps = [
        (0.25, "上传制度\nPDF"),
        (2.55, "文本切块\n写入索引"),
        (4.85, "识别职能\n与部门"),
        (7.15, "抽取或合并\n四类底稿"),
        (9.45, "更新并行\n容量"),
    ]
    for i, (x, t) in enumerate(steps):
        _box(ax, x, 0.55, 2.15, 1.95, t, GREEN if i % 2 == 0 else TEAL, 9)
        if i < len(steps) - 1:
            ax.annotate(
                "",
                xy=(x + 2.25, 1.5),
                xytext=(x + 2.15, 1.5),
                arrowprops=dict(arrowstyle="->", color=GRAY, lw=1.4),
            )
    fig.tight_layout()
    fig.savefig(OUT / "learn_flow.png", bbox_inches="tight", facecolor="white")
    plt.close()
