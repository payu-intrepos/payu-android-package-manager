#!/usr/bin/env python3
"""Build the in.payu dependency graph from published POMs.

Writes:
  repo/dependency-graph.json
  repo/dependency-graph.md   (Mermaid)
"""

from __future__ import annotations

import json

from lib import GROUP_ID, MAVEN_ROOT, iter_published_poms, parse_pom, scan_artifacts


def mermaid_id(artifact_id: str) -> str:
    return artifact_id.replace("-", "_").replace(".", "_")


def build_graph() -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    for pom_path in iter_published_poms():
        pom = parse_pom(pom_path)
        artifact_id = pom["artifactId"]
        if not artifact_id:
            continue
        node = nodes.setdefault(
            artifact_id,
            {
                "groupId": pom["groupId"] or GROUP_ID,
                "artifactId": artifact_id,
                "versions": [],
                "latest": pom["version"],
            },
        )
        if pom["version"] and pom["version"] not in node["versions"]:
            node["versions"].append(pom["version"])
            node["latest"] = pom["version"]

        for dep in pom["dependencies"]:
            if dep.get("groupId") != GROUP_ID:
                continue
            edges.append(
                {
                    "from": artifact_id,
                    "fromVersion": pom["version"],
                    "to": dep["artifactId"],
                    "toVersion": dep.get("version", ""),
                    "scope": dep.get("scope", "compile"),
                }
            )

    catalog = {item["artifactId"]: item for item in scan_artifacts()}
    for artifact_id, node in nodes.items():
        if artifact_id in catalog:
            node["latest"] = catalog[artifact_id]["latest"]
            node["versions"] = sorted(set(node["versions"]))

    unique_edges = []
    seen = set()
    for edge in edges:
        key = (edge["from"], edge["fromVersion"], edge["to"], edge["toVersion"])
        if key in seen:
            continue
        seen.add(key)
        unique_edges.append(edge)

    return {
        "groupId": GROUP_ID,
        "nodes": sorted(nodes.values(), key=lambda item: item["artifactId"]),
        "edges": sorted(unique_edges, key=lambda item: (item["from"], item["to"], item["fromVersion"])),
    }


def write_mermaid(graph: dict) -> str:
    latest_edges = {}
    latest_by_artifact = {node["artifactId"]: node["latest"] for node in graph["nodes"]}
    for edge in graph["edges"]:
        if edge["fromVersion"] != latest_by_artifact.get(edge["from"]):
            continue
        latest_edges[(edge["from"], edge["to"])] = edge

    lines = [
        "# in.payu dependency graph",
        "",
        "Latest published version of each artifact. Edges are `in.payu` only.",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    for node in graph["nodes"]:
        label = f"{node['artifactId']}\\n{node['latest']}"
        lines.append(f"    {mermaid_id(node['artifactId'])}[\"{label}\"]")
    for (source, target), edge in sorted(latest_edges.items()):
        version = edge["toVersion"] or "?"
        lines.append(
            f"    {mermaid_id(source)} -->|{version}| {mermaid_id(target)}"
        )
    lines.extend(["```", ""])
    return "\n".join(lines)


def main() -> None:
    graph = build_graph()
    json_path = MAVEN_ROOT / "dependency-graph.json"
    md_path = MAVEN_ROOT / "dependency-graph.md"
    json_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(write_mermaid(graph), encoding="utf-8")
    print(
        f"Wrote {json_path.name} ({len(graph['nodes'])} nodes, {len(graph['edges'])} edges) "
        f"and {md_path.name}"
    )


if __name__ == "__main__":
    main()
