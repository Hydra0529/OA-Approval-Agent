from __future__ import annotations

from xml.sax.saxutils import escape

from app.models.schema import ApprovalCase, ProcessTemplate


def template_to_bpmn(template: ProcessTemplate, case: ApprovalCase | None = None) -> str:
    """Deterministically convert a process template to BPMN 2.0 XML."""
    del case  # reserved for future highlight
    nodes = template.nodes
    if not nodes:
        return _empty_bpmn(template.name)

    ordered = _topo_order(template)
    x0, y0, dx = 180, 180, 170

    shapes: list[str] = []
    edges_xml: list[str] = []
    plane_shapes: list[str] = []
    plane_edges: list[str] = []

    shapes.append('<bpmn:startEvent id="StartEvent_1" name="开始"/>')
    plane_shapes.append(
        '<bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">'
        f'<dc:Bounds x="{x0 - dx}" y="{y0 + 22}" width="36" height="36"/>'
        "</bpmndi:BPMNShape>"
    )

    pos: dict[str, tuple[int, int]] = {}
    node_map = {n.id: n for n in nodes}
    for i, nid in enumerate(ordered):
        node = node_map[nid]
        x = x0 + i * dx
        y = y0
        pos[nid] = (x, y)
        shapes.append(f'<bpmn:task id="Task_{nid}" name="{escape(node.name)}"/>')
        plane_shapes.append(
            f'<bpmndi:BPMNShape id="Task_{nid}_di" bpmnElement="Task_{nid}">'
            f'<dc:Bounds x="{x}" y="{y}" width="120" height="80"/>'
            f"</bpmndi:BPMNShape>"
        )

    first = ordered[0]
    edges_xml.append(
        f'<bpmn:sequenceFlow id="Flow_start" sourceRef="StartEvent_1" targetRef="Task_{first}"/>'
    )
    plane_edges.append(
        f'<bpmndi:BPMNEdge id="Flow_start_di" bpmnElement="Flow_start">'
        f'<di:waypoint x="{x0 - dx + 36}" y="{y0 + 40}"/>'
        f'<di:waypoint x="{x0}" y="{y0 + 40}"/>'
        f"</bpmndi:BPMNEdge>"
    )

    for i in range(len(ordered) - 1):
        src, tgt = ordered[i], ordered[i + 1]
        fid = f"Flow_{src}_{tgt}"
        edges_xml.append(
            f'<bpmn:sequenceFlow id="{fid}" sourceRef="Task_{src}" targetRef="Task_{tgt}"/>'
        )
        sx, sy = pos[src]
        tx, ty = pos[tgt]
        plane_edges.append(
            f'<bpmndi:BPMNEdge id="{fid}_di" bpmnElement="{fid}">'
            f'<di:waypoint x="{sx + 120}" y="{sy + 40}"/>'
            f'<di:waypoint x="{tx}" y="{ty + 40}"/>'
            f"</bpmndi:BPMNEdge>"
        )

    last = ordered[-1]
    lx, ly = pos[last]
    shapes.append('<bpmn:endEvent id="EndEvent_1" name="结束"/>')
    edges_xml.append(
        f'<bpmn:sequenceFlow id="Flow_end" sourceRef="Task_{last}" targetRef="EndEvent_1"/>'
    )
    plane_edges.append(
        f'<bpmndi:BPMNEdge id="Flow_end_di" bpmnElement="Flow_end">'
        f'<di:waypoint x="{lx + 120}" y="{ly + 40}"/>'
        f'<di:waypoint x="{lx + dx}" y="{ly + 40}"/>'
        f"</bpmndi:BPMNEdge>"
    )
    plane_shapes.append(
        '<bpmndi:BPMNShape id="EndEvent_1_di" bpmnElement="EndEvent_1">'
        f'<dc:Bounds x="{lx + dx}" y="{ly + 22}" width="36" height="36"/>'
        "</bpmndi:BPMNShape>"
    )

    process_name = escape(template.name)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
 xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
 xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
 xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
 id="Definitions_{template.id}" targetNamespace="http://oa-agent.local/bpmn">
  <bpmn:process id="Process_{template.id}" name="{process_name}" isExecutable="false">
    {"".join(shapes)}
    {"".join(edges_xml)}
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_{template.id}">
      {"".join(plane_shapes)}
      {"".join(plane_edges)}
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>
"""


def _topo_order(template: ProcessTemplate) -> list[str]:
    if not template.nodes:
        return []
    node_ids = {n.id for n in template.nodes}
    adj: dict[str, list[str]] = {n.id: [] for n in template.nodes}
    indeg = {n.id: 0 for n in template.nodes}
    for e in template.edges:
        if e.source in node_ids and e.target in node_ids:
            # For layout, include all edges once (ignore duplicate targets)
            if e.target not in adj[e.source]:
                adj[e.source].append(e.target)
                indeg[e.target] += 1
    order_index = {n.id: i for i, n in enumerate(template.nodes)}
    # Prefer template order for branches: follow node list order as primary path
    return [n.id for n in template.nodes]


def _empty_bpmn(name: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
 xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
 xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
 id="Definitions_empty" targetNamespace="http://oa-agent.local/bpmn">
  <bpmn:process id="Process_empty" name="{escape(name)}" isExecutable="false">
    <bpmn:startEvent id="StartEvent_1" name="开始"/>
  </bpmn:process>
</bpmn:definitions>
"""
