"""Export a thesis-style scheme report that only describes implemented capabilities."""
from __future__ import annotations

import shutil
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from app.scripts.gen_scheme_figures import OUT as FIG_DIR
from app.scripts.gen_scheme_figures import (
    fig_architecture,
    fig_division,
    fig_learn_flow,
    fig_submit_flow,
    fig_system,
)

STYLE_SRC = Path(__file__).resolve().parents[3] / "docs" / "OA审批智能体_技术方案_V1.0.docx"
REPO = Path(__file__).resolve().parents[3] / "docs" / "OA审批智能体_技术方案_V2.0.docx"
DESK = Path(r"C:\Users\Jhy13\Desktop") / "OA审批智能体_技术方案_V2.0.docx"
HARRY = Path(r"C:\Users\Jhy13\Desktop\Harry\科研竞赛\AI Agent") / "OA审批智能体_技术方案_V2.0.docx"
EAST = qn("w:eastAsia")


def _ea(run, name="宋体"):
    run.font.name = "Times New Roman"
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = run._element.rPr.rFonts
    rfonts.set(EAST, name)


def _blank_from_template(dest: Path) -> Document:
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = STYLE_SRC if STYLE_SRC.exists() else None
    if src:
        shutil.copy(src, dest)
        doc = Document(str(dest))
        body = doc.element.body
        for child in list(body):
            if child.tag != qn("w:sectPr"):
                body.remove(child)
        return doc
    return Document()


def h1(doc, text):
    doc.add_paragraph(text, style="Heading 1")


def h2(doc, text):
    doc.add_paragraph(text, style="Heading 2")


def h3(doc, text):
    doc.add_paragraph(text, style="Heading 3")


def p(doc, text, style="Normal"):
    doc.add_paragraph(text, style=style)


def caption(doc, text):
    try:
        doc.add_paragraph(text, style="Caption")
    except KeyError:
        doc.add_paragraph(text)


def add_figure(doc, path: Path, title: str):
    if not path.exists():
        return
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = para.add_run()
    run.add_picture(str(path), width=Cm(14.6))
    caption(doc, title)


def add_table(doc, headers, rows, title: str):
    caption(doc, title)
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    table.autofit = True
    for i, head in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = head
        for para in cell.paragraphs:
            for run in para.runs:
                run.bold = True
                run.font.size = Pt(10.5)
                _ea(run, "黑体")
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = table.rows[ri + 1].cells[ci]
            cell.text = str(val)
            for para in cell.paragraphs:
                for run in para.runs:
                    run.font.size = Pt(10.5)
                    _ea(run)
    doc.add_paragraph("", style="Normal")


def cover(doc):
    for _ in range(3):
        doc.add_paragraph("", style="Normal")
    t1 = doc.add_paragraph("公司OA审批智能体系统", style="Title Style")
    t1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t2 = doc.add_paragraph("技术方案", style="Title Style")
    t2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for _ in range(2):
        e = doc.add_paragraph("", style="Body Text")
        e.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph("从规章制度学习审批路径并按申报材料生成办理方案", style="Body Text")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for r in sub.runs:
        r.bold = True
        _ea(r, "黑体")
        r.font.size = Pt(14)
    for _ in range(4):
        e = doc.add_paragraph("", style="Body Text")
        e.alignment = WD_ALIGN_PARAGRAPH.CENTER
    v = doc.add_paragraph("版本：V3.0", style="Body Text")
    v.alignment = WD_ALIGN_PARAGRAPH.CENTER
    d = doc.add_paragraph("2026年9月", style="Body Text")
    d.alignment = WD_ALIGN_PARAGRAPH.CENTER


def ch_abstract(doc):
    h1(doc, "摘要")
    p(
        doc,
        "企业内部审批长期依赖人工对照规章制度确定路径与材料。制度文本与申报材料分离，金额层级、外业许可等要求不易在提交时一次对齐，导致路径配置僵化或事后补件。本方案设计并实现一套本地可运行的 OA 审批智能辅助系统：以规章制度 PDF 为流程知识来源，以申报文件为实例输入，生成当单审批路径，并对受控作业进行合规闸门控制，同时提供项目群清单、部门负荷日历、流程图与分析报告。",
    )
    p(
        doc,
        "系统采用浏览器/服务器结构。表现层使用 React 与 Vite，应用服务层使用 FastAPI，数据层采用本地 JSON、YAML 与 PDF 文件，不依赖业务数据库与真实 OA。制度检索采用词法 TF 余弦，而非向量数据库。大模型通过 OpenAI 兼容接口按需调用，用于制度抽取、申报解析、当地所需材料推断与报告撰写；未配置接口密钥时，上述环节降级为规则与模板，清单与推演仍可运行。所谓智能体是按职责划分的同步处理模块，不是独立多智能体运行时。",
    )
    p(
        doc,
        "本文按方案报告体例组织：首先说明背景与需求，再给出总体架构、技术路线、业务流程与系统划分，随后按分系统叙述功能、处理过程与数据管理，最后给出接口及集成方案，并以已经跑通的金额分层与合规缺件场景作验证。文中阈值、接口与存储结构均与当前实现一致。",
    )
    p(doc, "关键词：OA 审批；流程生成；制度学习；合规审查；大模型辅助")


def ch_background(doc):
    h1(doc, "背景概述")
    h2(doc, "课题背景")
    p(
        doc,
        "办公自动化系统中的审批配置通常先绘制固定模板，再按类型套用。该方式适合路径稳定的报销、请假等业务，但难以覆盖两类变化：其一，金额或天数变化后，制度要求增加的审定层级不同；其二，立项类外业项目往往涉及空域、占道、水域等属地许可，申报书一般只描述作业内容与地点，并不列出当地应提交的文件。人工读制度、读申报、再决定路径和缺件，成本高且不易复现。",
    )
    p(
        doc,
        "本课题面向上述问题，建设一套可在本机演示的智能辅助系统。系统不替代正式 OA 的待办与权限，而是在提交阶段完成三件事：从制度文本形成可执行的流程知识，从申报材料生成本单路径，并在需要时给出法务审核所需的额外材料清单。演示入口为 http://127.0.0.1:5173/，服务接口前缀为 http://127.0.0.1:8000/api。",
    )

    h2(doc, "建设目标")
    add_table(
        doc,
        ["目标", "含义"],
        [
            ["制度可学习", "上传管理办法 PDF 后更新检索索引、部门清单、并行容量及四类底稿"],
            ["申报可解析", "读取立项书或说明文件，抽取标题、金额、地点、部门等字段"],
            ["路径可生成", "立项按金额门槛搭链；报销、采购、合同、请假复制规范底稿并按条件边分流"],
            ["合规可闸门", "根据作业内容推断当地许可材料，缺件则停滞在法务审查节点"],
            ["进度可观察", "项目群清单给出下一步与计划周期，日历给出部门忙闲，详情给出流程图与报告"],
        ],
        "表1  建设目标",
    )

    h2(doc, "建设范围")
    p(
        doc,
        "本方案的交付形态是本机前后端演示程序。单据由页面提交或脚本写入，不接入真实 OA，不提供用户登录与权限隔离，不训练或微调大模型。制度样本为公开管理办法及补充规定，存储全部落在本地文件。智能体名称用于划分职责，一次请求内顺序调用、共享同一进程。",
    )

    h2(doc, "方案论证")
    p(
        doc,
        "在确定总体方案时，曾对照三类常见做法。第一，从历史审批日志做流程挖掘。本课题没有真实 OA 流水，知识来源只能是制度文本，因此采用“制度学习 + 按单生成”，而不是日志挖掘。第二，采用独立多智能体框架（多进程协商、工具市场等）。本系统的角色数量有限、调用顺序固定，拆成独立运行时并不能增加可验证能力，因此将角色实现为同步模块。第三，采用向量数据库做制度检索。演示环境需要避免额外服务与模型下载，故采用切块后的词法 TF 余弦索引；检索稳定性弱于带中文分词的向量方案，但足以支撑当前规模的制度库。",
    )
    p(
        doc,
        "大模型定位为可选增强，而不是路由引擎。是否增加总经理与董事长、是否插入合规节点、部门日历如何着色，均由确定性规则计算。模型负责从自然语言中抽取字段、推断材料名称和撰写报告。该划分保证无密钥时系统仍可演示，也避免把审批层级交给模型自由发挥。",
    )


def ch_requirements(doc):
    h1(doc, "需求分析")
    h2(doc, "角色分析")
    p(
        doc,
        "实现上不区分登录账号，但业务上存在两类逻辑角色。申报人上传立项或报销等材料，查看清单、日历、缺件原因，并补充附件。制度管理员上传管理办法，使部门、并行容量和四类底稿随制度更新。两类操作共用同一界面，后文按功能而不是按账号描述。",
    )

    h2(doc, "功能需求")
    add_table(
        doc,
        ["编号", "需求项", "说明"],
        [
            ["F1", "制度入库", "接收 PDF，完成切块索引、职能识别、部门合并与底稿更新"],
            ["F2", "申报受理", "接收 PDF 或文本，抽取业务字段，允许标题、金额、部门留空由程序补全"],
            ["F3", "路径生成", "按业务类型与金额生成节点序列，立项与四类常规业务采用不同策略"],
            ["F4", "合规闸门", "识别受控作业并给出所需当地材料；缺件停滞，补件后复审"],
            ["F5", "项目群监控", "清单展示当前节点、下一步、停滞原因与计划起止"],
            ["F6", "部门负荷", "按角色映射部门，按并行上限给出空闲、忙碌、饱和"],
            ["F7", "可视化与解释", "输出 BPMN 流程图及基于事实的分析报告"],
            ["F8", "评测", "对四类底稿的条件边做金标准下一步检验"],
            ["F9", "维护", "删除单据及其按单生成的路径文件"],
        ],
        "表2  功能需求",
    )

    h2(doc, "约束需求")
    p(
        doc,
        "流程知识必须来自规章制度，而不是虚构节点。部门名称必须落在制度识别清单中，禁止任意手填。密钥只保存在本地环境文件，不进入源码。演示数据不得包含真实员工隐私。报销底稿与立项门槛以当前实现为准：报销在财务节点后以 1 万元区分出纳与财务负责人；立项默认以 500 万元区分是否增加总经理与董事长。制度文本中若另有五十万元加签表述，尚未写入上述条件边。",
    )

    h2(doc, "业务用例")
    p(
        doc,
        "主用例有两条。制度学习用例：管理员上传管理办法，系统完成入库并反馈切块数量、识别到的职能和部门变化。申报办理用例：申报人上传立项书或说明，系统生成清单项；若识别到受控作业且材料不足，清单显示停滞，申报人补充附件后复审。监控用例依附于第二条，用户通过日历与详情观察负荷和路径，不单独改变单据状态。",
    )


def ch_overall(doc, fig_arch: Path, fig_div: Path, fig_biz: Path, fig_learn: Path, fig_map: Path):
    h1(doc, "总体设计思路")
    h2(doc, "总体架构")
    p(
        doc,
        "系统采用经典的三层结构。表现层负责清单、日历、表单与图形展示，不在浏览器内计算路径。应用服务层集中处理制度学习、申报生成、合规审查、推演与报告。数据层以文件保存制度原文、流程底稿、单据实例、检索索引和组织参数。外部依赖只有两类：可选的大模型 HTTP 接口，以及合规说明所用的公开网页检索；二者失败时均有本地降级。",
    )
    add_figure(doc, fig_arch, "图1  系统总体架构")
    p(
        doc,
        "该结构的选择与建设范围一致：没有独立的消息总线、没有微服务注册，也没有单独的分析中心。前后端通过 HTTP JSON 集成，前端开发服务器将 /api 反向代理到应用服务，从而在本机形成完整闭环。",
    )
    add_figure(doc, fig_map, "图2  实现映射（目录与职责）")

    h2(doc, "技术路线")
    add_table(
        doc,
        ["层次", "技术选择", "选取理由"],
        [
            ["表现层", "React、Vite、bpmn-js", "单页即可覆盖清单、窗口与流程图，开发服务器便于代理接口"],
            ["应用服务", "FastAPI、Pydantic", "接口与数据模型同处一处，便于校验上传与单据结构"],
            ["流程表示", "节点—边—条件 YAML", "可被推演引擎求值，也可按单复制后改写"],
            ["制度检索", "切块 + 词法 TF 余弦", "无需向量库与嵌入模型，适合本机演示"],
            ["文档解析", "PDF 文本抽取", "制度与申报的主要输入形式"],
            ["大模型", "OpenAI 兼容 Chat Completions", "可切换通义、DeepSeek 等云端接口，不绑定单一厂商"],
            ["持久化", "JSON / YAML / PDF 文件", "无数据库安装成本，结构对演示透明"],
        ],
        "表3  技术路线",
    )
    p(
        doc,
        "技术路线强调可运行与可核对，而不是生产级吞吐。词法检索对同义改写敏感，文件存储不支持并发事务，这些限制在接口与后续工作中一并说明，不在总体设计中写成已具备的能力。",
    )

    h2(doc, "业务流程")
    p(
        doc,
        "业务上存在两条主干。第一条是制度学习：管理办法进入系统后，先抽取文本并切块建立索引，再识别其所属职能类别与部门名称，对报销、采购、合同、请假四类尝试生成或合并底稿，并解析“并行工作数”一类语句以更新日历容量。不属于四类的制度只入库，避免把保密、薪酬等文件误做成审批流。",
    )
    add_figure(doc, fig_learn, "图3  制度学习主流程")
    p(
        doc,
        "第二条是申报办理：系统读取申报正文，抽取字段并检索相关制度片段，按类型生成本单路径，再进行合规审查，最后写入单据并刷新清单与日历。立项不套用四类底稿，而是按金额门槛组装节点；其余类型复制规范底稿，由条件边决定后继。合规审查在识别到受控作业时插入法务节点。",
    )
    add_figure(doc, fig_biz, "图4  申报办理主流程")

    h2(doc, "系统划分")
    p(
        doc,
        "按照“学习—受理—审查—推演—展示”将系统划分为五个分系统。制度学习分系统维护流程知识与组织参数。申报与路径生成分系统把一份申报变成可执行的节点序列。合规审查分系统解决当地材料问题。监控推演分系统计算下一步、时间线、负荷与停滞。展示交互分系统提供页面与图表，不拥有另一套业务规则。",
    )
    add_figure(doc, fig_div, "图5  系统划分")
    add_table(
        doc,
        ["分系统", "主要输入", "主要输出"],
        [
            ["制度学习", "管理办法 PDF", "检索索引、部门清单、四类底稿、并行容量"],
            ["申报与路径生成", "申报文件、底稿与制度片段", "当单路径 YAML、单据字段"],
            ["合规审查", "申报正文、附件名、地点", "所需材料、缺件列表、联网说明"],
            ["监控推演", "单据与路径", "下一步、时间线、日历格子、停滞原因"],
            ["展示交互", "上述输出", "清单、日历、BPMN、报告、维护操作"],
        ],
        "表4  分系统输入输出",
    )


def ch_subsystems(doc):
    h1(doc, "分系统设计")
    h2(doc, "制度学习分系统")
    h3(doc, "功能模块")
    p(
        doc,
        "本分系统包含四个模块。文档解析模块从 PDF 得到纯文本。检索构建模块按长度切块，统计中文二字以上词与英文标记的词频，写入政策索引。组织识别模块从正文提取部门名称，并解析并行工作数，合并进部门清单。模板学习模块按文件名判断是否属于报销、采购、合同、请假；若属于，则调用抽取或启发式规则生成该类底稿，并与已有底稿按节点编号合并。",
    )
    h3(doc, "详细设计")
    p(
        doc,
        "检索采用词法余弦：查询与切块均表示为词频向量，取相似度最高的若干段供后续使用。模板学习优先尝试大模型输出 JSON 流程；失败则用规则生成，避免上传制度后没有任何底稿更新。职能识别依赖文件名与关键词对照表，不属于四类则只保留索引。并行容量默认因部门而异，例如总经办为 1、采购部为 2、财务部为 3；制度中出现“建议并行工作数为 N”时覆盖对应部门。",
    )
    h3(doc, "与界面的关系")
    p(
        doc,
        "页面“上传制度”触发本分系统。返回结果包括切块数、识别到的职能和部门变化，供管理员确认学习是否生效。日历在下一次刷新时读取更新后的并行上限。",
    )

    h2(doc, "申报与路径生成分系统")
    h3(doc, "功能模块")
    p(
        doc,
        "申请解析模块从合并后的正文得到标题、类别、金额、城市、区域、部门、申请人、设备与作业线索。制度检索模块用上述字段构造查询，取不超过六段制度。路径生成模块按类别分支：立项现场组装；其余类型深拷贝规范底稿并另存为当单路径。",
    )
    h3(doc, "详细设计")
    p(
        doc,
        "字段抽取优先请求大模型输出 JSON，失败或无密钥时改用规则：金额依次匹配“数字+万”“预算…数字”“数字+元”；城市在封闭词表中查找，并识别一环、二环、核心城区等表述；部门必须命中已登记名称。类别由文件名或正文中的立项、航拍、测绘、请假、合同、采购、报销等词决定。",
    )
    p(
        doc,
        "立项路径至少包含项目申报提交、部门经理审核、立项备案。金额达到门槛时，在经理与备案之间插入总经理审批与董事长审定。门槛优先取制度片段中与立项或项目投资相关的金额；取不到则使用 5_000_000 元。因此，预算 3 万元与 64 万元的路径相同，640 万元增加高管节点。报销、采购、合同、请假复制底稿后，由推演分系统按条件边求值：报销在财务节点后，金额不低于 1 万元到财务负责人，否则到出纳；采购在预算审核后，不低于 5 万元到总经理；合同在部门总监后，不低于 10 万元到总经理；请假按天数等字段分支。",
    )
    p(
        doc,
        "若合规分系统给出受控作业或所需材料，路径生成在归档前插入“合规与法务审查”节点，角色为法务专员。当单路径以 dyn- 前缀保存，与四类规范底稿分离，避免一次申报改写公共模板。",
    )

    h2(doc, "合规审查分系统")
    h3(doc, "功能模块")
    p(
        doc,
        "本分系统解决申报书通常不写材料清单的问题。作业识别模块用关键词覆盖无人机、封路或占道、垂钓或捕捞三类。材料推断模块在配置了接口密钥时调用大模型，要求根据作业内容、地点和设备列出当地许可或报备文件，而不是等待正文出现“需提供××”。检索说明模块按城市与作业主题查询公开网页，失败则使用本地条目。缺件判定模块用附件文件名及“已附/未附”表述与材料名称核对。",
    )
    h3(doc, "详细设计")
    p(
        doc,
        "关键词规则始终执行，作为三类常见作业的保底。大模型结果与规则结果按作业名称合并去重：规则防止模型漏报这三类，模型负责规则表以外的作业，例如河道清淤、危化品、爆破等，并给出可与文件名核对的材料名称。模型只影响材料清单，不改写金额路由。调用失败时退回纯规则，不中断受理。",
    )
    p(
        doc,
        "缺件时单据当前节点置于合规节点，停滞编码为 missing_docs。补充附件后按已保存的材料清单重新核对文件名，不再次调用大模型。北京且申报写明中心城区或二环以内时，说明中标注属地限制通常更严。联网检索不是裁决依据，只作为页面上的公开信息补充。",
    )

    h2(doc, "监控推演分系统")
    h3(doc, "功能模块")
    p(
        doc,
        "路径解析模块从节点、边和网关条件得到一条线性序列。下一步模块取当前节点之后的第一点。时间线模块按各节点工作时限累加工作日，跳过周末。负荷模块把角色映射到部门，统计某日占用窗口内的不重复单据数。停滞诊断模块按缺件、关键岗位部门饱和、超并行容量的优先级给出原因。",
    )
    h3(doc, "详细设计")
    p(
        doc,
        "条件表达式在受控上下文中求值，可用字段包括金额、部门、类别及单据扩展字段。角色映射规则为：财务类角色归财务部，总经理与董事长归总经办，法务专员归法务部，其余归申请人所在部门。负荷分级为：零为空闲，未达上限一半为偏空闲，达到一半为忙碌，达到或超过上限为饱和；超出部分记为额外延迟工作日。日历只允许选择当天及以前的日期。进行中的当前节点会把占用窗口至少延伸到当天，上限四十五天，避免超时后日历占用消失。",
    )

    h2(doc, "展示交互分系统")
    p(
        doc,
        "本分系统不维护第二套业务规则。清单、日历、申报窗口、制度上传、材料补充、删除项目、评测横幅均读取应用服务的结果。流程图由节点与边生成 BPMN 2.0，前端只负责呈现。分析报告优先由大模型根据事实字典撰写；无密钥时用模板拼接路径、时间线、制度片段和本单生成说明。引用制度来自检索前四段，不是制度全文。",
    )

    h2(doc, "数据管理设计")
    p(
        doc,
        "系统不使用关系库或文档库服务，而用目录约定管理数据。该选择使演示可复制：拷贝数据目录即可带走制度、底稿和单据。代价是没有事务与统一备份，并发写入依赖单机使用前提。",
    )
    add_table(
        doc,
        ["数据对象", "存储位置", "主要内容"],
        [
            ["制度原文", "data/policies", "管理办法 PDF，单文件不超过 12MB"],
            ["检索索引", "data/index/policy_index.json", "切块文本、词频、来源文件名"],
            ["规范底稿", "data/templates", "报销、采购、合同、请假四类 YAML"],
            ["当单路径", "data/generated", "标识以 dyn- 开头的 YAML"],
            ["审批单据", "data/cases", "每单一份 JSON，含字段、历史、停滞信息"],
            ["申报附件", "data/applications", "提交与补充的 PDF、TXT"],
            ["组织参数", "data/org/departments.json", "部门名称与并行工作数"],
            ["学习记录", "data/org 知识文件", "已识别职能"],
            ["评测集", "data/eval/gold.jsonl", "十条下一步金标准"],
        ],
        "表5  数据对象与存储",
    )
    add_table(
        doc,
        ["对象", "关键属性"],
        [
            ["流程模板", "标识、名称、类别、节点（编号、名称、角色、工作时限）、边（起点、终点、条件）、网关、制度引用"],
            ["审批单据", "编号、标题、模板标识、类别、金额、部门、申请人、当前节点、状态、扩展字段、历史事件、停滞编码与说明"],
            ["扩展字段", "城市、设备、受控作业、所需材料、缺件、制度命中、合规发现、来源文件、是否使用大模型"],
        ],
        "表6  核心数据结构",
    )


def ch_interface(doc):
    h1(doc, "接口及集成方案")
    h2(doc, "内部接口")
    p(
        doc,
        "表现层与应用服务层通过 REST 风格 HTTP 接口交换 JSON。开发环境下由 Vite 将浏览器的 /api 请求代理到本机 8000 端口，因此页面相对路径与后端路由一致。上传类接口使用 multipart 表单，查询类接口使用 GET。应用服务内部各分系统以函数调用集成本地模块，不经过网络。",
    )
    add_table(
        doc,
        ["方法", "路径", "集成作用"],
        [
            ["GET", "/api/health", "探活，返回模板数、单据数、是否启用大模型"],
            ["GET/POST", "/api/policies、/policies/upload、/policies/ask", "制度列表、入库学习、按问题检索"],
            ["GET/POST", "/api/templates、/templates/extract", "底稿查询与从指定制度再抽取"],
            ["GET", "/api/portfolio、/api/cases/{id}", "清单与详情（时间线、BPMN、报告、停滞）"],
            ["POST", "/api/cases/submit-pack", "读取申报文件并生成单据，主受理入口"],
            ["POST", "/api/cases/submit", "按已有底稿标识提交，部门必须在清单中"],
            ["POST", "/api/cases/{id}/supplement", "补充附件并复审缺件"],
            ["POST/DELETE", "/api/cases/delete、/api/cases/{id}", "删除单据及对应当单路径"],
            ["GET", "/api/calendar", "月历及某日各部门负荷"],
            ["GET", "/api/departments、/api/knowledge", "部门清单与已学习职能"],
            ["GET", "/api/eval/run", "运行金标准评测"],
        ],
        "表7  内部接口一览",
    )

    h2(doc, "外部接口")
    p(
        doc,
        "大模型接口遵循 OpenAI 兼容的 Chat Completions。地址、模型名与密钥写在应用服务环境文件中，当前常用通义千问等云端模型。调用分为 JSON 模式与文本模式：前者用于制度模板、申报字段与材料清单，后者用于分析报告。未配置密钥时客户端直接返回空，由各分系统走规则分支。",
    )
    p(
        doc,
        "公开网页检索用于补充城市与作业主题的合规说明，请求公开搜索页的 HTML 结果。网络失败或无结果时，使用本地预置说明。该接口不写入单据路径，只影响详情中的说明文字。",
    )

    h2(doc, "集成与运行")
    p(
        doc,
        "完整系统由两个进程组成，必须同时运行。应用服务在 backend 目录启动，监听 127.0.0.1:8000；表现层在 frontend 目录启动开发服务器，监听 127.0.0.1:5173。环境前提为 Python 3.10 及以上虚拟环境、已安装后端依赖，以及已执行前端依赖安装。可选配置大模型密钥。",
    )
    p(doc, "后端启动（Windows 命令提示符）：")
    p(doc, "cd /d <仓库根目录>\\backend")
    p(doc, ".venv\\Scripts\\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000")
    p(doc, "前端启动：")
    p(doc, "cd /d <仓库根目录>\\frontend")
    p(doc, "npm run dev")
    p(
        doc,
        "启动成功后访问 http://127.0.0.1:5173/，接口说明页为 http://127.0.0.1:8000/docs。停止时在对应窗口使用 Ctrl+C。本方案不包含容器编排、反向代理生产配置与监控告警。",
    )

    h2(doc, "异常与降级")
    add_table(
        doc,
        ["情形", "处理"],
        [
            ["未配置或调用大模型失败", "字段用规则抽取，材料用三类关键词，报告用模板拼接"],
            ["网页检索失败", "使用本地城市与作业说明"],
            ["部门不在清单中", "拒绝提交或回退到清单内名称"],
            ["制度不属于四类", "只建立索引，不新建审批底稿"],
            ["补充材料仍不匹配", "保持缺件停滞，不后移当前节点"],
        ],
        "表8  集成降级策略",
    )


def ch_validation(doc):
    h1(doc, "典型场景验证")
    h2(doc, "立项金额分层")
    p(
        doc,
        "采用同一套城区低空无人机航拍测绘立项申报书，仅改变预算。按当前立项规则，3 万元与 64 万元低于 500 万元，路径为申报提交、部门经理、立项备案；640 万元增加总经理与董事长。三份材料均描述北京二环以内无人机作业且未附飞行或空域申请，因此同时触发合规闸门。该场景验证“金额只影响高管链、不影响外业闸门”。",
    )

    h2(doc, "当地材料推断")
    p(
        doc,
        "申报书一般不罗列许可清单。关键词规则保证无人机、封路或占道、垂钓或捕捞三类在无密钥时仍能插入法务节点。配置密钥后，模型根据作业与地点补充材料名称；补充附件时以文件名与材料关键词匹配为通过条件。纯室内报销、请假等无外业描述时，不应插入该闸门。",
    )

    h2(doc, "制度变更与负荷")
    p(
        doc,
        "上传含并行工作数建议的制度后，对应部门上限变化。在办单据占用不变时，上限降低会使日历由忙碌转为饱和，详情中的额外延迟增加。该场景验证组织参数与展示分系统之间的闭环。",
    )

    h2(doc, "条件边评测")
    p(
        doc,
        "评测集共十条，覆盖四类底稿在给定当前节点与金额下的下一步，例如报销在财务节点时 3200 元到出纳、15800 元到财务负责人。评测不覆盖立项 500 万元高管链，也不覆盖合规缺件，边界需要在结论中写明。",
    )


def ch_conclusion(doc):
    h1(doc, "结论与后续工作")
    h2(doc, "结论")
    p(
        doc,
        "本方案给出一种以制度文本为知识来源、以申报文件为实例输入的审批辅助设计：用可执行底稿与按单生成相结合处理常规业务与立项分层，用规则加可选大模型处理当地材料推断，用文件型数据层支撑本机演示。系统划分与接口边界清楚，无密钥时主路径仍可运行，有密钥时材料推断不依赖申报书自带清单。",
    )

    h2(doc, "已实现与未实现")
    add_table(
        doc,
        ["类别", "内容"],
        [
            ["已实现", "制度学习、申报生成、合规闸门、清单与日历、BPMN 与报告、删除与评测、本机启动"],
            ["未实现", "真实 OA 对接、登录权限、向量检索、知识图谱、独立多智能体运行时、生产部署与备份"],
            ["与制度文本的差异", "报销底稿未写入五十万元加签；立项默认 500 万元才增加高管"],
            ["无密钥时的合规", "仅三类关键词保底，开放域作业无法推断"],
        ],
        "表9  实现边界",
    )

    h2(doc, "后续工作")
    p(
        doc,
        "若需与制度中的五十万元分界对齐，应修改路径生成与报销底稿条件，而不是增加额外抽象层。若制度规模扩大，可将词法索引替换为中文向量检索。若进入实际办公环境，需要独立的事件接入、身份认证和数据库，而不是继续把全部单据写入本地 JSON。",
    )


def main():
    fig_system()
    fig_submit_flow()
    fig_architecture()
    fig_division()
    fig_learn_flow()
    fig_arch = FIG_DIR / "architecture.png"
    fig_div = FIG_DIR / "division.png"
    fig_biz = FIG_DIR / "submit_flow.png"
    fig_learn = FIG_DIR / "learn_flow.png"
    fig_map = FIG_DIR / "system_real.png"

    REPO.parent.mkdir(parents=True, exist_ok=True)
    doc = _blank_from_template(REPO)
    cover(doc)
    ch_abstract(doc)
    ch_background(doc)
    ch_requirements(doc)
    ch_overall(doc, fig_arch, fig_div, fig_biz, fig_learn, fig_map)
    ch_subsystems(doc)
    ch_interface(doc)
    ch_validation(doc)
    ch_conclusion(doc)
    doc.save(str(REPO))
    shutil.copy(REPO, DESK)
    HARRY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO, HARRY)
    print(REPO)
    print(DESK)
    print(HARRY)


if __name__ == "__main__":
    main()
