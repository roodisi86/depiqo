"""Summarises Maestro results (JUnit files and screenshots) as report.md and report.html.

    python3 .github/scripts/maestro_report.py <results dir> <title>

Looks for */junit/*.xml and */screenshots/*.png under <results dir> (one subfolder per language run). Appends the
Markdown to $GITHUB_STEP_SUMMARY when set. Always exits 0: it only reports; the run itself decides pass or fail.
"""
import html
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def cases(xml_path):
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as exc:
        return [(xml_path.stem, "unreadable", str(exc), "")]
    out = []
    for tc in root.iter("testcase"):
        failure = tc.find("failure")
        error = tc.find("error")
        bad = failure if failure is not None else error
        status = "FAILED" if bad is not None else ("skipped" if tc.find("skipped") is not None else "ok")
        msg = (bad.get("message") or bad.text or "").strip() if bad is not None else ""
        out.append((tc.get("name") or xml_path.stem, status, msg[:500], tc.get("time") or ""))
    return out or [(xml_path.stem, "no test cases", "", "")]


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: maestro_report.py <results dir> <title>")
    base = Path(sys.argv[1])
    title = sys.argv[2]
    runs = sorted({p.parent.parent for p in base.rglob("junit/*.xml")} | {p.parent.parent for p in base.rglob("screenshots/*.png")})
    md = [f"## {title}", ""]
    body = [f"<h1>{html.escape(title)}</h1>"]
    if not runs:
        md.append("Geen Maestro-resultaten gevonden (de run is gestopt voor de flows begonnen; zie de log van de job).")
        body.append("<p>Geen Maestro-resultaten gevonden.</p>")
    total = failed = 0
    for run in runs:
        rel = run.relative_to(base)
        md += [f"### {rel}", "", "| Flow | Resultaat | Tijd (s) | Melding |", "|---|---|---|---|"]
        body.append(f"<h2>{html.escape(str(rel))}</h2><table border=1 cellpadding=4><tr><th>Flow</th><th>Resultaat</th><th>Tijd</th><th>Melding</th></tr>")
        for xml_path in sorted((run / "junit").glob("*.xml")):
            for name, status, msg, secs in cases(xml_path):
                total += 1
                failed += status not in ("ok", "skipped")
                cell = msg.replace("|", "\\|").replace("\n", " ")
                md.append(f"| {name} | {status} | {secs} | {cell} |")
                body.append(f"<tr><td>{html.escape(name)}</td><td>{html.escape(status)}</td><td>{html.escape(secs)}</td><td>{html.escape(msg)}</td></tr>")
        body.append("</table>")
        results = run / "results.txt"
        if results.exists():
            md += ["", "```", results.read_text().strip(), "```"]
        shots = sorted((run / "screenshots").glob("*.png"))
        md += ["", f"Schermafdrukken: {len(shots)} (in het artifact, map `{rel}/screenshots`)", ""]
        for s in shots:
            r = s.relative_to(base)
            body.append(f"<figure style='display:inline-block;margin:8px'><img src='{html.escape(str(r))}' width=240>"
                        f"<figcaption>{html.escape(s.name)}</figcaption></figure>")
    md.insert(2, f"**{total - failed} van {total} flows geslaagd.**" if total else "")
    (base / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (base / "report.html").write_text("<!doctype html><meta charset=utf-8><title>" + html.escape(title) + "</title>"
                                      + "\n".join(body), encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
