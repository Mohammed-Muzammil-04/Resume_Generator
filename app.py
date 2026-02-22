from flask import Flask, render_template, request, jsonify, send_file
from groq import Groq
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import os, json, uuid, io, re
from datetime import datetime
from dotenv import load_dotenv

app = Flask(__name__)

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# 🔴 MISSING LINE (CAUSE OF 500 ERROR)
client = Groq(api_key=GROQ_API_KEY)

DB_FILE = "resumes_db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return []
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

def clean(text):
    chars = {
        "\u2018":"'","\u2019":"'","\u201c":'"',"\u201d":'"',
        "\u2013":"-","\u2014":"-","\u2022":"-","\u2026":"...",
        "\u00a0":" ","\u00b7":"-","\u2015":"-","\u2012":"-",
    }
    for k,v in chars.items():
        text = text.replace(k,v)
    return text.encode("latin-1", errors="replace").decode("latin-1")

# ─────────────────────────────────────────────────────────────
#  RESUME PDF — clean template style
# ─────────────────────────────────────────────────────────────
def build_resume_pdf(data):
    pdf = FPDF()
    pdf.set_margins(0, 0, 0)
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()

    W  = 210
    M  = 12
    CW = W - 2*M

    # ── HEADER: Name left, contact right ─────────────────────
    header_h = 34
    pdf.set_fill_color(255,255,255)
    pdf.rect(0, 0, W, header_h, "F")

    name = clean(data.get("name","Your Name"))
    pdf.set_xy(M, 9)
    pdf.set_font("Helvetica","B", 20)
    pdf.set_text_color(15,15,15)
    pdf.cell(105, 10, name)

    # Contact block - right side
    contact = []
    if data.get("phone"):    contact.append(clean(data["phone"]))
    if data.get("email"):    contact.append(clean(data["email"]))
    if data.get("linkedin"): contact.append(clean(data["linkedin"]))
    if data.get("location"): contact.append(clean(data["location"]))

    pdf.set_font("Helvetica","", 8)
    pdf.set_text_color(60,60,60)
    cy = 8
    for c in contact:
        pdf.set_xy(M+105, cy)
        pdf.cell(CW-105, 5, c, align="R",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        cy += 5.5

    # Divider
    pdf.set_y(header_h)
    pdf.set_draw_color(20,20,20)
    pdf.set_line_width(0.7)
    pdf.line(M, header_h, W-M, header_h)
    pdf.set_line_width(0.2)
    pdf.ln(3)

    # ── HELPERS ──────────────────────────────────────────────
    def section_title(txt):
        pdf.set_x(M)
        pdf.set_font("Helvetica","B",10.5)
        pdf.set_text_color(15,15,15)
        pdf.cell(CW, 5.5, txt, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_draw_color(160,160,160)
        pdf.line(M, pdf.get_y(), W-M, pdf.get_y())
        pdf.ln(2.5)

    def bullet_point(txt):
        pdf.set_x(M+3)
        pdf.set_font("Helvetica","",9)
        pdf.set_text_color(50,50,50)
        pdf.cell(5, 5, "-", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_x(M+9)
        pdf.multi_cell(CW-9, 5, clean(txt))

    def tag_row(items):
        """Draw items as grey bordered tag boxes, wrapping to next line."""
        x = M
        y = pdf.get_y()
        pdf.set_font("Helvetica","",8.5)
        for item in items:
            item = clean(item.strip())
            if not item: continue
            tw = pdf.get_string_width(item) + 8
            if x + tw > W - M:
                x  = M
                y += 6.5
            pdf.set_fill_color(242,242,242)
            pdf.set_draw_color(190,190,190)
            pdf.set_text_color(35,35,35)
            pdf.rect(x, y, tw, 5.8, "FD")
            pdf.set_xy(x+1, y+0.8)
            pdf.cell(tw-2, 4.2, item)
            x += tw + 3
        pdf.set_y(y + 6.5)

    # ── SUMMARY ──────────────────────────────────────────────
    summary = clean(data.get("summary","").strip())
    if summary:
        section_title("Summary")
        pdf.set_x(M)
        pdf.set_font("Helvetica","",9)
        pdf.set_text_color(50,50,50)
        pdf.multi_cell(CW, 5, summary)
        pdf.ln(2)

    # ── SKILLS ───────────────────────────────────────────────
    skills = [s for s in data.get("skills",[]) if s.strip()]
    if skills:
        section_title("Skills")
        tag_row(skills)
        pdf.ln(1)

    # ── EDUCATION ────────────────────────────────────────────
    education = data.get("education",[])
    if education:
        section_title("Education")
        for edu in education:
            inst  = clean(edu.get("institution",""))
            deg   = clean(edu.get("degree",""))
            yr    = clean(edu.get("year",""))
            grade = clean(edu.get("grade",""))
            loc   = clean(edu.get("location",""))

            # Institution (bold left) + Location (italic right)
            pdf.set_x(M)
            pdf.set_font("Helvetica","B",10)
            pdf.set_text_color(15,15,15)
            pdf.cell(CW-45, 5.5, inst, new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.set_font("Helvetica","I",8.5)
            pdf.set_text_color(110,110,110)
            pdf.cell(45, 5.5, loc, align="R",
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            # Degree (semi-bold)
            if deg:
                pdf.set_x(M)
                pdf.set_font("Helvetica","B",9)
                pdf.set_text_color(40,40,40)
                pdf.cell(CW, 5, deg, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            # Year + Grade
            sub = "  |  ".join(filter(None,[yr,grade]))
            if sub:
                pdf.set_x(M)
                pdf.set_font("Helvetica","",8.5)
                pdf.set_text_color(110,110,110)
                pdf.cell(CW, 4.5, sub, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2)

    # ── EXPERIENCE ───────────────────────────────────────────
    experience = data.get("experience",[])
    if experience:
        section_title("Experience")
        for exp in experience:
            company = clean(exp.get("company",""))
            role    = clean(exp.get("role",""))
            start   = clean(exp.get("start",""))
            end     = clean(exp.get("end",""))
            loc     = clean(exp.get("location",""))
            bullets = exp.get("bullets",[])

            dates = (start + (" - " + end if end else "")).strip()

            # Company bold left, location italic right
            pdf.set_x(M)
            pdf.set_font("Helvetica","B",10)
            pdf.set_text_color(15,15,15)
            pdf.cell(CW-45, 5, company, new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.set_font("Helvetica","I",8)
            pdf.set_text_color(110,110,110)
            pdf.cell(45, 5, loc, align="R",
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            # Role
            if role:
                pdf.set_x(M)
                pdf.set_font("Helvetica","B",9)
                pdf.set_text_color(40,40,40)
                pdf.cell(CW, 4.5, role, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            # Dates
            if dates:
                pdf.set_x(M)
                pdf.set_font("Helvetica","",8)
                pdf.set_text_color(110,110,110)
                pdf.cell(CW, 4, dates, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            for b in bullets:
                bullet_point(b)
            pdf.ln(2)

    # ── PROJECTS ─────────────────────────────────────────────
    projects = data.get("projects",[])
    if projects:
        section_title("Projects")
        for proj in projects:
            pname = clean(proj.get("name",""))
            tech  = clean(proj.get("tech",""))
            header = pname + (" | " + tech if tech else "")
            pdf.set_x(M)
            pdf.set_font("Helvetica","B",9.5)
            pdf.set_text_color(20,20,20)
            pdf.multi_cell(CW, 5.5, header)
            for b in proj.get("bullets",[]):
                bullet_point(b)
            pdf.ln(2)

    # ── CERTIFICATIONS ───────────────────────────────────────
    certs = data.get("certifications",[])
    if certs:
        section_title("Certifications")
        for c in certs:
            bullet_point(c)
        pdf.ln(2)

    # ── LANGUAGES ────────────────────────────────────────────
    langs = data.get("languages",[])
    if langs:
        section_title("Language")
        lang_str = ",  ".join([clean(l.strip()) for l in langs if l.strip()])
        pdf.set_x(M)
        pdf.set_font("Helvetica","",9)
        pdf.set_text_color(50,50,50)
        pdf.multi_cell(CW, 5, lang_str)
        pdf.ln(1)

    buf = io.BytesIO(pdf.output())
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────
#  COVER LETTER PDF
# ─────────────────────────────────────────────────────────────
def build_cover_pdf(name, job_title, content):
    pdf = FPDF()
    pdf.set_margins(20,20,20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    W=210; M=20; CW=W-2*M

    pdf.set_fill_color(26,71,42)
    pdf.rect(0,0,W,40,"F")
    pdf.set_xy(0,9)
    pdf.set_font("Helvetica","B",18)
    pdf.set_text_color(255,255,255)
    pdf.cell(W,11,clean(name.upper()),
             new_x=XPos.LMARGIN,new_y=YPos.NEXT,align="C")
    pdf.set_font("Helvetica","",9)
    pdf.set_text_color(190,230,190)
    pdf.cell(W,7,clean(f"Cover Letter - {job_title}"),
             new_x=XPos.LMARGIN,new_y=YPos.NEXT,align="C")
    pdf.ln(14)

    for raw in content.split("\n"):
        s = clean(re.sub(r'\*\*(.+?)\*\*',r'\1',raw.strip()))
        if not s:
            pdf.ln(3); continue
        pdf.set_x(M)
        pdf.set_font("Helvetica","",10)
        pdf.set_text_color(50,50,50)
        pdf.multi_cell(CW,6,s)

    buf = io.BytesIO(pdf.output())
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────
#  PARSE AI TEXT → structured dict
# ─────────────────────────────────────────────────────────────
def parse_structured(resume_text, raw):
    d = {
        "name":     raw.get("name",""),
        "email":    raw.get("email",""),
        "phone":    raw.get("phone",""),
        "linkedin": raw.get("linkedin",""),
        "location": raw.get("location",""),
        "summary":"", "skills":[], "experience":[],
        "education":[], "projects":[], "certifications":[], "languages":[]
    }

    # Pull skills directly from form data (most reliable)
    raw_skills = raw.get("skills","")
    if raw_skills:
        for sk in re.split(r'[,\n]', raw_skills):
            sk = sk.strip().lstrip("-* ")
            if sk: d["skills"].append(sk)

    # Pull languages directly from form data
    raw_langs = raw.get("languages","")
    if raw_langs:
        for l in re.split(r'[,\n]', raw_langs):
            l = l.strip()
            if l: d["languages"].append(l)

    SECTION_MAP = {
        "SUMMARY":"summary","PROFILE":"summary","OBJECTIVE":"summary",
        "PROFESSIONAL SUMMARY":"summary",
        "EXPERIENCE":"experience","WORK EXPERIENCE":"experience",
        "PROFESSIONAL EXPERIENCE":"experience","INTERNSHIPS":"experience",
        "EDUCATION":"education","ACADEMIC BACKGROUND":"education",
        "SKILLS":"skills_ai","TECHNICAL SKILLS":"skills_ai",
        "PROJECTS":"projects","KEY PROJECTS":"projects",
        "CERTIFICATIONS":"certifications","CERTIFICATES":"certifications",
        "LANGUAGES":"languages_ai","LANGUAGE":"languages_ai",
    }

    current_section = None
    current_entry   = None
    current_bullets = []
    summary_lines   = []

    def flush():
        nonlocal current_entry, current_bullets
        if current_entry is None: return
        current_entry["bullets"] = current_bullets[:]
        if current_section == "experience":   d["experience"].append(current_entry)
        elif current_section == "education":  d["education"].append(current_entry)
        elif current_section == "projects":   d["projects"].append(current_entry)
        current_entry   = None
        current_bullets = []

    for line in resume_text.split("\n"):
        s = line.strip()
        if not s: continue

        # Section header detection
        key = s.upper().rstrip(":").strip()
        if key in SECTION_MAP:
            flush()
            current_section = SECTION_MAP[key]
            continue

        if current_section == "summary":
            summary_lines.append(s)

        elif current_section in ("skills_ai",) and not d["skills"]:
            # Only use AI skills if form didn't provide them
            for sk in re.split(r'[,|]', s):
                sk = sk.strip().lstrip("-* ")
                if sk: d["skills"].append(sk)

        elif current_section == "experience":
            if s.startswith("- ") or s.startswith("* "):
                current_bullets.append(s[2:].strip())
            elif "|" in s:
                flush()
                parts = [p.strip() for p in s.split("|")]
                date_str = parts[2] if len(parts)>2 else ""
                date_parts = [x.strip() for x in date_str.split("-")]
                current_entry = {
                    "role":    parts[0] if parts else "",
                    "company": parts[1] if len(parts)>1 else "",
                    "start":   date_parts[0] if date_parts else "",
                    "end":     date_parts[1] if len(date_parts)>1 else "",
                    "location":parts[3] if len(parts)>3 else "",
                }
                current_bullets = []
            else:
                # Plain line: company then role then date pattern
                if current_entry is None:
                    flush()
                    current_entry = {"company":s,"role":"","start":"","end":"","location":""}
                    current_bullets = []
                elif not current_entry.get("role"):
                    current_entry["role"] = s
                elif not current_entry.get("start"):
                    dp = [x.strip() for x in s.split("-")]
                    current_entry["start"] = dp[0]
                    current_entry["end"]   = dp[1] if len(dp)>1 else ""

        elif current_section == "education":
            if "|" in s:
                flush()
                parts = [p.strip() for p in s.split("|")]
                current_entry = {
                    "degree":      parts[0] if parts else "",
                    "institution": parts[1] if len(parts)>1 else "",
                    "year":        parts[2] if len(parts)>2 else "",
                    "grade":       parts[3] if len(parts)>3 else "",
                    "location":    parts[4] if len(parts)>4 else "",
                }
                current_bullets = []
                flush()
            else:
                if current_entry is None:
                    current_entry = {"institution":s,"degree":"","year":"","grade":"","location":""}
                    current_bullets = []
                elif not current_entry.get("degree"):
                    current_entry["degree"] = s
                elif not current_entry.get("year"):
                    # Check if it's a year/grade line
                    nums = re.findall(r'[\d.]+', s)
                    if nums: current_entry["year"] = nums[0]
                    if len(nums)>1: current_entry["grade"] = nums[1]
                elif not current_entry.get("location"):
                    current_entry["location"] = s

        elif current_section == "projects":
            if s.startswith("- ") or s.startswith("* "):
                current_bullets.append(s[2:].strip())
            else:
                flush()
                if "|" in s:
                    parts = [p.strip() for p in s.split("|")]
                    current_entry = {"name":parts[0],"tech":parts[1] if len(parts)>1 else ""}
                else:
                    current_entry = {"name":s,"tech":""}
                current_bullets = []

        elif current_section == "certifications":
            cert = s.lstrip("-* ").strip()
            if cert and cert.upper() not in SECTION_MAP:
                d["certifications"].append(cert)

        elif current_section == "languages_ai" and not d["languages"]:
            # Only use if form didn't give us languages
            for l in re.split(r'[,]', s):
                l = l.strip().lstrip("-* ")
                if l and l.upper() not in SECTION_MAP and len(l) < 40:
                    d["languages"].append(l)

    flush()
    d["summary"] = " ".join(summary_lines)

    # Fallback: parse education from raw form data
    if not d["education"] and raw.get("education_entries"):
        for e in raw.get("education_entries",[]):
            d["education"].append(e)

    # Fallback: parse experience from raw form data
    if not d["experience"] and raw.get("experience_entries"):
        for e in raw.get("experience_entries",[]):
            d["experience"].append(e)

    return d


def parse_output(output):
    r = output.find("--- RESUME ---")
    c = output.find("--- COVER LETTER ---")
    if r!=-1 and c!=-1:
        return (output[r+len("--- RESUME ---"):c].strip(),
                output[c+len("--- COVER LETTER ---"):].strip())
    return output.strip(), output.strip()


SYSTEM_PROMPT = """You are a professional resume writer. Follow this exact format:

SECTION HEADERS (ALL CAPS on their own line):
SUMMARY
EXPERIENCE
EDUCATION
SKILLS
PROJECTS
CERTIFICATIONS
LANGUAGES

SUMMARY RULES — CRITICAL:
- Write exactly 4-5 sentences
- NEVER third person. NEVER "Mohammed is..." or "He is..." or "[Name] is..."
- ALWAYS first-person implied: start with role/adjective
- Good example: "Detail-oriented Front-End Developer with 2+ years of experience in web development and generative AI. Proficient in Python, Flask, HTML, CSS, and JavaScript. Proven ability to build responsive, user-friendly interfaces and automate workflows. Eager to contribute innovative solutions to a dynamic engineering team."

EXPERIENCE — pipe format, max 3 bullets per job:
Role Title | Company Name | Start Date - End Date | City
- Bullet achievement starting with action verb
- Bullet achievement with impact
- Bullet achievement

EDUCATION — pipe format:
Degree | Institution | Year | Grade | City

SKILLS: comma-separated on ONE line only

PROJECTS — max 2 bullets each:
Project Name | Tech Stack
- What it does and impact

CERTIFICATIONS:
- Cert name

LANGUAGES: ALL on ONE comma-separated line e.g. English: Fluent, Tamil: Native, Urdu: Fluent

RULES:
- No paragraphs in Experience/Education
- No markdown (no ** or ##)
- Use real candidate details only
- Keep concise to fit ONE page
- Separate with: --- RESUME --- and --- COVER LETTER ---"""


@app.route("/")
def home():
    return render_template("index.html")

@app.route("/history")
def history():
    return render_template("history.html")

@app.route("/generate", methods=["POST"])
def generate():
    try:
        data        = request.json
        name        = data.get("name","Candidate")
        job_title   = data.get("job_title","")
        template    = data.get("template","modern")
        full_prompt = data.get("full_prompt")

        if not full_prompt:
            skills     = data.get("skills","")
            experience = data.get("experience","")
            education  = data.get("education","")
            job_desc   = data.get("job_desc","")
            jd = f"\nTailor to:\n{job_desc}" if job_desc.strip() else ""
            full_prompt = (f"Create RESUME and COVER LETTER.\nName: {name}\n"
                           f"Job: {job_title}\nSkills: {skills}\n"
                           f"Experience: {experience}\nEducation: {education}{jd}\n"
                           f"Start with --- RESUME ---")

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role":"system","content":SYSTEM_PROMPT},
                {"role":"user",  "content":full_prompt}
            ],
            max_tokens=2000
        )
        output = response.choices[0].message.content

        record = {
            "id": str(uuid.uuid4())[:8], "name":name,
            "job_title":job_title, "template":template,
            "output":output,
            "raw": {
                "name":name, "job_title":job_title,
                "email":    data.get("email",""),
                "phone":    data.get("phone",""),
                "linkedin": data.get("linkedin",""),
                "location": data.get("location",""),
                "skills":   data.get("skills",""),
                "languages":data.get("languages",""),
                "experience_entries": data.get("experience_entries",[]),
                "education_entries":  data.get("education_entries",[]),
            },
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        try:
            db=load_db(); db.insert(0,record); save_db(db)
        except:
            pass
        return jsonify({"output":output,"id":record["id"]})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/history")
def api_history():
    db=load_db()
    return jsonify([{"id":r["id"],"name":r["name"],"job_title":r["job_title"],
                     "template":r["template"],"created_at":r["created_at"]} for r in db])

@app.route("/api/history/<rid>")
def api_history_detail(rid):
    db=load_db()
    r=next((x for x in db if x["id"]==rid),None)
    return jsonify(r) if r else (jsonify({"error":"Not found"}),404)

@app.route("/api/history/<rid>", methods=["DELETE"])
def delete_record(rid):
    db=load_db(); save_db([r for r in db if r["id"]!=rid])
    return jsonify({"success":True})

@app.route("/download-resume-pdf", methods=["POST"])
def download_resume_pdf():
    data=request.json
    output=data.get("output","")
    raw=data.get("raw",{})
    name=data.get("name","Candidate")
    resume_text,_=parse_output(output)
    try:
        structured=parse_structured(resume_text,raw)
        buf=build_resume_pdf(structured)
        safe=re.sub(r'\s+','_',name)
        return send_file(buf,as_attachment=True,
                         download_name=f"{safe}_Resume.pdf",
                         mimetype="application/pdf")
    except Exception as e:
        import traceback; traceback.print_exc()
        return f"PDF error: {e}",500

@app.route("/download-cover-pdf", methods=["POST"])
def download_cover_pdf():
    data=request.json
    output=data.get("output","")
    name=data.get("name","Candidate")
    job_title=data.get("job_title","")
    _,cover_text=parse_output(output)
    try:
        buf=build_cover_pdf(name,job_title,cover_text)
        safe=re.sub(r'\s+','_',name)
        return send_file(buf,as_attachment=True,
                         download_name=f"{safe}_Cover_Letter.pdf",
                         mimetype="application/pdf")
    except Exception as e:
        return f"PDF error: {e}",500

if __name__=="__main__":
    app.run(debug=True)