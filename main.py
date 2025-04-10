"""
A Kano Modell alapjai röviden
Alapvető jellemzők (Must-be)
Ezek a funkciók természetesen elvártak: a hiányuk elégedetlenséget okoz, viszont a meglétük nem növeli az ügyfél elégedettségét.

Teljesítmény jellemzők (Performance)
Itt a funkció teljesítménye egyenesen arányos az ügyfél elégedettségével: minél jobb a funkció, annál elégedettebb az ügyfél.

Élmény jellemzők (Delighters)
Ezek olyan extra funkciók, amelyek nem elvártak, de ha jelen vannak, jelentős pozitív hatást gyakorolnak az ügyfél élményére, ha hiányoznak, általában nem okoznak elégedetlenséget.

"""

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

write_lock = asyncio.Lock()

app = FastAPI()

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

CONFIG_DIR = "config"  # A YAML fájlok könyvtára

response_mapping = {
    "Nagyon elégedett / nagyon fontos": 5,
    "Inkább elégedett / valamennyire fontos": 4,
    "Semleges": 3,
    "Kevéssé elégedett / kevéssé fontos": 2,
    "Egyáltalán nem elégedett / nem fontos": 1
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
    return templates.TemplateResponse("choose.html", {"request": request, "config_files": config_files})

# --- Normál felhasználók űrlap oldala ---
@app.get("/form", response_class=HTMLResponse)
async def form_get(request: Request, project: str = None):
    if not project:
        return RedirectResponse(url="/", status_code=303)
    data = load_questions(project)
    questions = data.get("questions", [])
    project_name = data.get("project", ["N/A"])[0]
    return templates.TemplateResponse("form.html", {
        "request": request,
        "questions": questions,
        "project": project_name,
        "config_file": project
    })

# --- Beküldés ---
@app.post("/submit", response_class=HTMLResponse)
async def submit(request: Request):
    form = await request.form()
    timestamp = datetime.datetime.now().isoformat()
    config_file = form.get("config_file", "default.yaml")
    csv_filename = get_csv_filename(config_file)
    
    answers = []
    for key in form.keys():
        if key.startswith("q_") and (key.endswith("_functional") or key.endswith("_dysfunctional")):
            parts = key.split("_")
            if len(parts) < 3:
                continue
            question_id = parts[1]
            qtype = parts[2]
            function_text = form.get(f"q_{question_id}_function", "N/A")
            answer = form[key]
            answers.append([timestamp, question_id, function_text, qtype, answer])
    
    # Ha a CSV még nem létezik, hozzuk létre a fejlécet
    if not os.path.exists(csv_filename):
        async with write_lock:
            with open(csv_filename, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Question_ID", "Function", "Question_Type", "Answer"])
    
    # Írjuk felül az adatokat a CSV-be a lock segítségével
    async with write_lock:
        with open(csv_filename, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in answers:
                writer.writerow(row)
    
    return RedirectResponse(url="/form?project=" + config_file, status_code=303)

# --- Admin választóoldala: Csak az admin férhet hozzá, itt az értékeléshez vezető linkek vannak ---
@app.get("/admin/choose", response_class=HTMLResponse)
async def admin_choose(request: Request, username: str = Depends(verify_admin)):
    config_files = list_config_files()
    # Az admin választóoldal csak az értékelésre vezető linkeket mutatja
    return templates.TemplateResponse("choose_admin.html", {"request": request, "config_files": config_files})

# --- Admin értékelési oldal ---
@app.get("/admin/evaluation", response_class=HTMLResponse)
async def evaluation(request: Request, project: str = None, username: str = Depends(verify_admin)):
    if not project:
        return RedirectResponse(url=f"/admin/choose?username={username}", status_code=303)
    csv_filename = get_csv_filename(project)
    if not os.path.exists(csv_filename):
        evaluation = []
    else:
        responses = []
        with open(csv_filename, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["Numeric_Answer"] = response_mapping.get(row["Answer"], None)
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

    # Csoportosítás és rendezés:
    must_be = [x for x in evaluation if x["Category"] == "Must-be (Basic)"]
    one_dim = [x for x in evaluation if x["Category"] == "One-dimensional (Performance)"]
    attractive = [x for x in evaluation if x["Category"] == "Attractive (Delight)"]

    # Rendezés kategórián belül:
    # Must-be: magasabb Delta érték előrébb (nagyobb elégedetlenség hiány esetén)
    must_be_sorted = sorted(must_be, key=lambda x: x["Delta"] if x["Delta"] is not None else 0, reverse=True)
    # One-dimensional: abszolút Delta érték alapján (nagyobb eltérés erősebb hatást jelez)
    one_dim_sorted = sorted(one_dim, key=lambda x: abs(x["Delta"]) if x["Delta"] is not None else 0, reverse=True)
    # Attractive: mivel Delta negatív, rendezés növekvő sorrendben, így a nagyobb (abszolút) negatív érték előrébb kerül
    attractive_sorted = sorted(attractive, key=lambda x: x["Delta"] if x["Delta"] is not None else 0)

    ordered_evaluation = must_be_sorted + one_dim_sorted + attractive_sorted

    return templates.TemplateResponse("evaluation.html", {
        "request": request,
        "evaluation": ordered_evaluation,
        "config_file": project
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
