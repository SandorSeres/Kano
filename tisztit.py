import csv
import yaml

csv_input = "./prompt_engineering_tanfolyam.csv"
yaml_file = "./config/prompt_engineering_tanfolyam.yaml"  # állítsd be a pontos nevet
csv_output = "cleaned_and_filled.csv"

# 1. Töltsük be a YAML-ból az ID → Function párokat
with open(yaml_file, encoding="utf-8") as f:
    config = yaml.safe_load(f)
    id_to_function = {
        str(q["id"]): q["function"]
        for q in config["questions"]
    }

# 2. Olvassuk be a CSV-t, és töltsük ki az üres Function mezőket
with open(csv_input, mode="r", encoding="utf-8") as infile, \
     open(csv_output, mode="w", encoding="utf-8", newline="") as outfile:

    reader = csv.DictReader(infile)
    fieldnames = reader.fieldnames
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()

    for row in reader:
        if not row["Function"].strip():
            qid = row["Question_ID"]
            row["Function"] = id_to_function.get(qid, "ISMERETLEN FUNKCIÓ")
        writer.writerow(row)

print(f"Tisztított és kitöltött CSV mentve: {csv_output}")
