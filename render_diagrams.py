import re
import os

def generate_diagram_viewer(input_md_path, output_html_path):
    """
    Reads a markdown file, extracts Mermaid blocks, and generates a beautiful
    HTML viewer using the Mermaid.js CDN.
    """
    if not os.path.exists(input_md_path):
        print(f"Error: Input file '{input_md_path}' not found.")
        return

    print(f"Reading diagrams from: {input_md_path}")
    
    with open(input_md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Regex to find all mermaid blocks: ```mermaid ... ```
    mermaid_blocks = re.findall(r'```mermaid\s+(.*?)\s+```', content, re.DOTALL)

    if not mermaid_blocks:
        print("No Mermaid diagrams found in the markdown file.")
        return

    # Extract titles (headers just above the code blocks)
    # This is a bit heuristic: looks for the last # Header before the block.
    # We'll just number them for simplicity in this script.
    
    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MindSpace Diagrams Viewer</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        body {{
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background: #0f172a;
            color: #f8fafc;
            line-height: 1.6;
            margin: 0;
            padding: 40px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        h1 {{ color: #38bdf8; margin-bottom: 40px; }}
        .diagram-container {{
            background: rgba(30, 41, 59, 0.7);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 40px;
            width: 100%;
            max-width: 1000px;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(8px);
        }}
        .diagram-title {{
            font-size: 1.2rem;
            color: #94a3b8;
            margin-bottom: 20px;
            text-align: center;
            border-bottom: 1px solid #334155;
            padding-bottom: 10px;
        }}
        .mermaid {{
            background: white; /* Mermaid themes often look better on light bg in dark mode containers */
            padding: 20px;
            border-radius: 8px;
        }}
    </style>
</head>
<body>
    <h1>MindSpace Architecture Visualizer</h1>
    """

    for i, block in enumerate(mermaid_blocks, 1):
        html_template += f"""
    <div class="diagram-container">
        <div class="diagram-title">Diagram #{i}</div>
        <pre class="mermaid">
{block}
        </pre>
    </div>
        """

    html_template += """
    <script>
        mermaid.initialize({ 
            startOnLoad: true,
            theme: 'default',
            securityLevel: 'loose'
        });
    </script>
</body>
</html>
"""

    with open(output_html_path, 'w', encoding='utf-8') as f:
        f.write(html_template)
    
    print(f"Success! Created diagram viewer at: {os.path.abspath(output_html_path)}")

if __name__ == "__main__":
    # Point this to your artifact path
    INPUT_FILE = "mindspace_diagrams.md"
    OUTPUT_FILE = "view_diagrams.html"
    
    generate_diagram_viewer(INPUT_FILE, OUTPUT_FILE)
