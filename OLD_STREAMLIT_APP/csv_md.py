import pandas as pd
import datetime
import sys

def csv_to_markdown(input_csv, output_md):
    # Read the CSV file into a DataFrame
    df = pd.read_csv(input_csv)

    # Generate YAML front matter with title and current date
    date_str = datetime.date.today().isoformat()
    yaml_header = f"""---
title: "Plasmid Library"
date: {date_str}
---

"""

    # Introductory text
    intro = "This is our plasmid library.\n\n"

    # Convert DataFrame to a Markdown-formatted table
    markdown_table = df.to_markdown(index=False)

    # Write everything to the output Markdown file
    with open(output_md, 'w', encoding='utf-8') as f:
        f.write(yaml_header)
        f.write(intro)
        f.write(markdown_table)
        f.write("\n")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python csv_to_markdown.py input.csv output.md")
        sys.exit(1)
    csv_to_markdown(sys.argv[1], sys.argv[2])
