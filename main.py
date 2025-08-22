from fastapi import FastAPI, Request, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import yaml
import csv
import os
import datetime
import statistics
import asyncio
import io
import re
from typing import Dict, Tuple, Optional
from collections import defaultdict, Counter

write_lock = asyncio.Lock()
app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# !!!!!!!!!!!!!!!!!!!!!!!!!!!
BUCKET_NAME = "kano-responses-kanoapp1"
# !!!!!!!!!!!!!!!!!!!!!!!!!!
CONFIG_DIR = "config"  # A YAML fájlok könyvtára

# --- Egyszerűsített (átlag+delta) mappingek ---
functional_mapping = {
    "Nagyon elégedett / nagyon fontos": 5,
    "Inkább elégedett / valamennyire fontos": 4,
    "Semleges": 3,
    "Kevéssé elégedett / kevéssé fontos": 2,
    "Egyáltalán nem elégedett / nem fontos": 1
}
dysfunctional_mapping = {
    "Nagyon elégedetlen / alapvető hiányosság": 5,
    "Elégedetlen / elég kritikus": 4,
    "Semleges": 3,
    "Nem nagyon érdekelne / kevésbé zavarna": 2,
    "Egyáltalán nem érdekelne / nem okozna gondot": 1
}

def list_config_files():
    return [file for file in os.listdir(CONFIG_DIR) if file.endswith((".yaml", ".yml"))]

def load_questions(yaml_file):
    path = os.path.join(CONFIG_DIR, yaml_file)
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_csv_filename(yaml_file):
    base = os.path.splitext(yaml_file)[0]
    return f"{base}.csv"

# Admin ellenőrzés: az adminhoz "admin" felhasználónév tartozik.
def verify_admin(username: str = Query(...)):
    if username != "admin":
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid username")
    return username

# --- Normál felhasználók választóoldala ("/") ---
@app.get("/", response_class=HTMLResponse)
async def choose_project(request: Request):
    config_files = list_config_files()
    projects = []
    for filename in config_files:
        try:
            data = load_questions(filename)
            project_name = data.get("project", ["Névtelen projekt"])[0]
            projects.append({"filename": filename, "project_name": project_name})
        except Exception as e:
            print(f"Hiba a(z) {filename} fájl beolvasásakor: {e}")
            projects.append({"filename": filename, "project_name": filename})  # fallback
    return templates.TemplateResponse("choose.html", {"request": request, "projects": projects})

# --- Normál felhasználók űrlap oldala ---
@app.get("/form", response_class=HTMLResponse)
async def form_get(request: Request, project: str = None):
    if not project:
        return RedirectResponse(url="/", status_code=303)
    data = load_questions(project)
    questions = data.get("questions", [])
    project_name = data.get("project", ["N/A"])[0]
    description = data.get("description", "")
    return templates.TemplateResponse("form.html", {
        "request": request,
        "questions": questions,
        "project": project_name,
        "config_file": project,
        "description": description
    })

# --- Beküldés ---
from google.cloud import storage
storage_client = storage.Client()

def upload_csv_to_gcs(bucket_name, destination_blob_name, file_contents: io.StringIO):
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_string(file_contents.getvalue(), content_type="text/csv")
    print(f"CSV uploaded to gs://{bucket_name}/{destination_blob_name}")

@app.post("/submit", response_class=HTMLResponse)
async def submit(request: Request):
    form = await request.form()
    timestamp = datetime.datetime.now().isoformat()
    config_file = form.get("config_file", "default.yaml")
    csv_filename = get_csv_filename(config_file)

    # Regex a kulcsokhoz, pl. q_1_functional vagy q_2a_dysfunctional
    pattern = re.compile(r"^q_([^_]+)_(functional|dysfunctional)$")

    answers = []
    for key in form.keys():
        match = pattern.match(key)
        if match:
            question_id = match.group(1)
            qtype = match.group(2)
            function_text = form.get(f"q_{question_id}_function", "N/A")
            answer = form[key]
            answers.append([timestamp, question_id, function_text, qtype, answer])

    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)

    # Fejléc csak akkor íródik, ha új a fájl
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(csv_filename)
    if not blob.exists():
        writer.writerow(["Timestamp", "Question_ID", "Function", "Question_Type", "Answer"])
    else:
        existing_data = blob.download_as_text()
        csv_buffer.write(existing_data)
        csv_buffer.write("\n")

    for row in answers:
        writer.writerow(row)

    async with write_lock:
        upload_csv_to_gcs(BUCKET_NAME, csv_filename, csv_buffer)

    return RedirectResponse(url="/thankyou", status_code=303)

@app.get("/thankyou", response_class=HTMLResponse)
async def thank_you(request: Request):
    return templates.TemplateResponse("thankyou.html", {"request": request})

# --- Admin választóoldala ---
@app.get("/admin/choose", response_class=HTMLResponse)
async def admin_choose(request: Request, username: str = Depends(verify_admin)):
    """
    A template (choose_admin.html) mostantól kaphat egy 'url' mezőt is a projektekhez,
    ami közvetlenül a KLASSZIKUS nézetre mutat. Ha a template nem használja, nincs gond.
    """
    config_files = list_config_files()
    projects = []
    for filename in config_files:
        try:
            data = load_questions(filename)
            project_name = data.get("project", ["Névtelen projekt"])[0]
            projects.append({
                "filename": filename,
                "project_name": project_name,
                # klasszikus Kano legyen az elsődleges cél
                "url": f"/admin/kano?project={filename}&username={username}"
            })
        except Exception as e:
            print(f"Hiba a(z) {filename} fájl beolvasásakor: {e}")
            projects.append({
                "filename": filename,
                "project_name": filename,
                "url": f"/admin/kano?project={filename}&username={username}"
            })
    return templates.TemplateResponse("choose_admin.html", {"request": request, "projects": projects})

# --- Admin értékelési oldal (egyszerűsített: átlag+delta) ---
@app.get("/admin/evaluation", response_class=HTMLResponse)
async def evaluation(request: Request, project: str = None, username: str = Depends(verify_admin)):
    if not project:
        return RedirectResponse(url=f"/admin/choose?username={username}", status_code=303)
    csv_filename = get_csv_filename(project)

    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(csv_filename)

    if not blob.exists():
        evaluation = []
    else:
        csv_text = blob.download_as_text()
        csv_buffer = io.StringIO(csv_text)
        responses = []
        reader = csv.DictReader(csv_buffer)
        for row in reader:
            # Az adott sorban a "Question_Type" alapján választjuk ki a megfelelő mapping-et
            if row["Question_Type"].lower() == "functional":
                row["Numeric_Answer"] = functional_mapping.get(row["Answer"], None)
            elif row["Question_Type"].lower() == "dysfunctional":
                row["Numeric_Answer"] = dysfunctional_mapping.get(row["Answer"], None)
            else:
                row["Numeric_Answer"] = None
            if row["Numeric_Answer"] is not None:
                responses.append(row)

        evaluation_data = {}
        for row in responses:
            key = (row["Question_ID"], row["Function"])
            if key not in evaluation_data:
                evaluation_data[key] = {"functional": [], "dysfunctional": []}
            qtype = row["Question_Type"].lower()
            if qtype == "functional":
                evaluation_data[key]["functional"].append(row["Numeric_Answer"])
            elif qtype == "dysfunctional":
                evaluation_data[key]["dysfunctional"].append(row["Numeric_Answer"])

        evaluation = []
        for (qid, func) in evaluation_data:
            func_scores = evaluation_data[(qid, func)]["functional"]
            dysfunc_scores = evaluation_data[(qid, func)]["dysfunctional"]
            if func_scores and dysfunc_scores:
                functional_avg = statistics.mean(func_scores)
                dysfunctional_avg = statistics.mean(dysfunc_scores)
                delta = dysfunctional_avg - functional_avg
                if delta > 0.1:
                    category = "Must-be (Basic)"
                elif delta < -0.1:
                    category = "Attractive (Delight)"
                else:
                    category = "One-dimensional (Performance)"
            else:
                functional_avg = None
                dysfunctional_avg = None
                delta = None
                category = "N/A"
            evaluation.append({
                "Question_ID": qid,
                "Function": func,
                "Functional_Average": functional_avg,
                "Dysfunctional_Average": dysfunctional_avg,
                "Delta": delta,
                "Category": category
            })

    must_be = [x for x in evaluation if x["Category"] == "Must-be (Basic)"]
    one_dim = [x for x in evaluation if x["Category"] == "One-dimensional (Performance)"]
    attractive = [x for x in evaluation if x["Category"] == "Attractive (Delight)"]

    must_be_sorted = sorted(must_be, key=lambda x: x["Delta"] if x["Delta"] is not None else 0, reverse=True)
    one_dim_sorted = sorted(one_dim, key=lambda x: abs(x["Delta"]) if x["Delta"] is not None else 0, reverse=True)
    attractive_sorted = sorted(attractive, key=lambda x: x["Delta"] if x["Delta"] is not None else 0)

    ordered_evaluation = must_be_sorted + one_dim_sorted + attractive_sorted

    return templates.TemplateResponse("evaluation.html", {
        "request": request,
        "evaluation": ordered_evaluation,
        "config_file": project
    })

# =========================
#   KLASSZIKUS KANO NÉZET
# =========================

def _norm(s: str) -> str:
    return " ".join((s or "").strip().casefold().split())

# A felirataid -> Kano skála jelek
FUNC_TO_KANO: Dict[str, str] = {
    _norm("Nagyon elégedett / nagyon fontos"): "L",
    _norm("Inkább elégedett / valamennyire fontos"): "L",
    _norm("Semleges"): "N",
    _norm("Kevéssé elégedett / kevéssé fontos"): "LW",
    _norm("Egyáltalán nem elégedett / nem fontos"): "D",
}
DYS_TO_KANO: Dict[str, str] = {
    _norm("Nagyon elégedetlen / alapvető hiányosság"): "D",
    _norm("Elégedetlen / elég kritikus"): "D",
    _norm("Semleges"): "N",
    _norm("Nem nagyon érdekelne / kevésbé zavarna"): "LW",
    _norm("Egyáltalán nem érdekelne / nem okozna gondot"): "L",
}

def map_func_answer_to_kano(a: str) -> Optional[str]:
    return FUNC_TO_KANO.get(_norm(a))

def map_dys_answer_to_kano(a: str) -> Optional[str]:
    return DYS_TO_KANO.get(_norm(a))

# Klasszikus 5×5-ös Kano táblázat (F x D -> kategória)
KANO_MATRIX: Dict[Tuple[str, str], str] = {
    ("L", "L"): "Q",  ("L", "N"): "A",  ("L", "LW"): "A",  ("L", "D"): "O",
    ("N", "L"): "R",  ("N", "N"): "I",  ("N", "LW"): "I",  ("N", "D"): "M",
    ("LW","L"): "R",  ("LW","N"): "I",  ("LW","LW"): "I",  ("LW","D"): "M",
    ("D", "L"): "R",  ("D", "N"): "R",  ("D", "LW"): "R",  ("D", "D"): "Q",
}

def classify_pair(func_kano: str, dys_kano: str) -> str:
    return KANO_MATRIX.get((func_kano, dys_kano), "Q")

def compute_better_worse(counts: Counter):
    """
    Better = (A + O) / (A+O+M+I)
    Worse  = - (M + O) / (A+O+M+I)
    R és Q nem szerepelnek a nevezőben.
    """
    denom = counts["A"] + counts["O"] + counts["M"] + counts["I"]
    if denom == 0:
        return None, None, 0
    better = (counts["A"] + counts["O"]) / denom
    worse = - (counts["M"] + counts["O"]) / denom
    return better, worse, denom

@app.get("/admin/kano", response_class=HTMLResponse)
async def kano_evaluation(request: Request, project: str = None, username: str = Depends(verify_admin)):
    """
    Klasszikus Kano aggregált kiértékelés (Respondent_ID nélkül):
    - a funkcionális és diszfunkcionális válaszok eloszlását kombinálja (szorzat),
    - így becsli a Kano kategória megoszlást (A/O/M/I/R/Q),
    - számolja a Better/Worse indexet is (R és Q nélkül).
    """
    if not project:
        return RedirectResponse(url=f"/admin/choose?username={username}", status_code=303)
    csv_filename = get_csv_filename(project)

    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(csv_filename)

    if not blob.exists():
        return templates.TemplateResponse("kano_evaluation.html", {
            "request": request,
            "config_file": project,
            "rows": [],
        })

    csv_text = blob.download_as_text()

    # Üres sorok kiszűrése (különben DictReader néha torz rekordot ad)
    lines = [ln for ln in csv_text.splitlines() if ln.strip()]
    if not lines:
        return templates.TemplateResponse("kano_evaluation.html", {
            "request": request,
            "config_file": project,
            "rows": [],
        })

    reader = csv.DictReader(io.StringIO("\n".join(lines)))

    per_q = defaultdict(lambda: {"F": Counter(), "D": Counter()})

    for row in reader:
        if not row:
            continue
        qid = (row.get("Question_ID") or "").strip()
        func_text = (row.get("Function") or "").strip()
        qtype = (row.get("Question_Type") or "").strip().casefold()
        ans = (row.get("Answer") or "").strip()
        if not qid or not func_text or not qtype or not ans:
            continue

        key = (qid, func_text)
        if qtype == "functional":
            k = map_func_answer_to_kano(ans)
            if k:
                per_q[key]["F"][k] += 1
        elif qtype == "dysfunctional":
            k = map_dys_answer_to_kano(ans)
            if k:
                per_q[key]["D"][k] += 1
        else:
            continue

    rows = []
    for (qid, func_label), data in per_q.items():
        F_counts = data["F"]
        D_counts = data["D"]

        kano_counts = Counter({"A":0,"O":0,"M":0,"I":0,"R":0,"Q":0})
        total_pairs = 0

        if not F_counts or not D_counts:
            rows.append({
                "Question_ID": qid,
                "Function": func_label,
                "counts": dict(kano_counts),
                "dominant": None,
                "better": None,
                "worse": None,
                "total_pairs": 0,
                "denom": 0,
            })
            continue

        for f_kano, f_c in F_counts.items():
            for d_kano, d_c in D_counts.items():
                cat = classify_pair(f_kano, d_kano)
                kano_counts[cat] += f_c * d_c
                total_pairs += f_c * d_c

        better, worse, denom = compute_better_worse(kano_counts)
        dominant = max(kano_counts.keys(), key=lambda k: kano_counts[k]) if total_pairs > 0 else None

        rows.append({
            "Question_ID": qid,
            "Function": func_label,
            "counts": dict(kano_counts),
            "dominant": dominant,
            "better": better,
            "worse": worse,
            "total_pairs": total_pairs,
            "denom": denom,
        })

    # --- RENDEZÉS: M → O → A → I → R → Q → N/A; csoporton belül denom desc, better desc, worse asc
    category_order = {"M": 0, "O": 1, "A": 2, "I": 3, "R": 4, "Q": 5, None: 6}
    def sort_key(r):
        cat_rank = category_order.get(r["dominant"], 6)
        denom = r["denom"] if r["denom"] is not None else 0
        better = r["better"] if r["better"] is not None else -1.0
        worse = r["worse"] if r["worse"] is not None else 1.0
        # elsődlegesen kategória, majd denom (desc), better (desc), worse (asc)
        return (cat_rank, -denom, -better, worse)

    rows_sorted = sorted(rows, key=sort_key)

    return templates.TemplateResponse("kano_evaluation.html", {
        "request": request,
        "config_file": project,
        "rows": rows_sorted,
    })

# --- Healthcheck ---
@app.get("/healthz", response_class=JSONResponse)
async def healthz():
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

