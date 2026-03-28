import calendar
import os
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


def load_env_file():
    if not ENV_FILE.exists():
        return

    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()


app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "reserva-escola-secret-key")
APP_TIMEZONE = ZoneInfo(os.getenv("APP_TIMEZONE", "America/Sao_Paulo"))

SQLITE_PATH = BASE_DIR / "reservas.db"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_ENGINE = "postgres" if DATABASE_URL.startswith(("postgres://", "postgresql://")) else "sqlite"

if DB_ENGINE == "postgres":
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "DATABASE_URL está configurada para PostgreSQL, mas o pacote 'psycopg[binary]' não está instalado."
        ) from exc


def adapt_query(query):
    if DB_ENGINE == "postgres":
        return query.replace("?", "%s")
    return query


def get_connection():
    if DB_ENGINE == "sqlite":
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def fetchall(conn, query, params=()):
    if DB_ENGINE == "sqlite":
        return conn.execute(query, params).fetchall()
    with conn.cursor() as cur:
        cur.execute(adapt_query(query), params)
        return cur.fetchall()


def fetchone(conn, query, params=()):
    if DB_ENGINE == "sqlite":
        return conn.execute(query, params).fetchone()
    with conn.cursor() as cur:
        cur.execute(adapt_query(query), params)
        return cur.fetchone()


def execute(conn, query, params=()):
    if DB_ENGINE == "sqlite":
        return conn.execute(query, params)
    with conn.cursor() as cur:
        cur.execute(adapt_query(query), params)
        return cur


def row_to_dict(row):
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return dict(row)


def rows_to_dicts(rows):
    return [row_to_dict(row) for row in rows]


def init_db():
    conn = get_connection()

    if DB_ENGINE == "sqlite":
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                senha_hash TEXT NOT NULL,
                perfil TEXT NOT NULL CHECK (perfil IN ('aluno', 'professor', 'admin')),
                criado_em TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS reservas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                area TEXT NOT NULL,
                data TEXT NOT NULL,
                inicio TEXT NOT NULL,
                fim TEXT NOT NULL
            )
            """,
        )
        conn.commit()

        columns = {row["name"] for row in fetchall(conn, "PRAGMA table_info(reservas)")}
        if "inicio" not in columns and "hora_inicio" in columns:
            execute(conn, "ALTER TABLE reservas RENAME COLUMN hora_inicio TO inicio")
        if "fim" not in columns and "hora_fim" in columns:
            execute(conn, "ALTER TABLE reservas RENAME COLUMN hora_fim TO fim")

        columns = {row["name"] for row in fetchall(conn, "PRAGMA table_info(reservas)")}
        if "user_id" not in columns:
            execute(conn, "ALTER TABLE reservas ADD COLUMN user_id INTEGER")
        conn.commit()
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id BIGSERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                senha_hash TEXT NOT NULL,
                perfil TEXT NOT NULL CHECK (perfil IN ('aluno', 'professor', 'admin')),
                criado_em TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS reservas (
                id BIGSERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                area TEXT NOT NULL,
                data TEXT NOT NULL,
                inicio TEXT NOT NULL,
                fim TEXT NOT NULL,
                user_id BIGINT REFERENCES usuarios(id) ON DELETE SET NULL
            )
            """,
        )
        conn.commit()

    admin_email = "admin@escola.local"
    admin_existe = fetchone(conn, "SELECT id FROM usuarios WHERE email = ?", (admin_email,))
    if admin_existe is None:
        execute(
            conn,
            """
            INSERT INTO usuarios (nome, email, senha_hash, perfil, criado_em)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "Administrador",
                admin_email,
                generate_password_hash("admin123"),
                "admin",
                datetime.now(APP_TIMEZONE).isoformat(timespec="seconds"),
            ),
        )
        conn.commit()

    if DB_ENGINE == "sqlite":
        usuarios_por_nome = {
            row["nome"]: row["id"]
            for row in fetchall(conn, "SELECT id, nome FROM usuarios")
        }
        reservas_sem_vinculo = fetchall(conn, "SELECT id, nome FROM reservas WHERE user_id IS NULL")
        for reserva in reservas_sem_vinculo:
            user_id = usuarios_por_nome.get(reserva["nome"])
            if user_id:
                execute(conn, "UPDATE reservas SET user_id = ? WHERE id = ?", (user_id, reserva["id"]))
        conn.commit()

    conn.close()


def horario_conflita(inicio_a, fim_a, inicio_b, fim_b):
    return inicio_a < fim_b and fim_a > inicio_b


def parse_reserva_datetime(data_str, hora_str):
    return datetime.strptime(f"{data_str} {hora_str}", "%Y-%m-%d %H:%M").replace(tzinfo=APP_TIMEZONE)


def get_calendar_context():
    hoje = datetime.now(APP_TIMEZONE)
    calendario = calendar.Calendar(firstweekday=0)
    semanas = calendario.monthdayscalendar(hoje.year, hoje.month)
    nomes_meses = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ]
    dias_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    return {
        "calendar_month": f"{nomes_meses[hoje.month - 1]} {hoje.year}",
        "calendar_today": hoje.strftime("%d/%m"),
        "calendar_weekdays": dias_semana,
        "calendar_weeks": semanas,
        "today_day": hoje.day,
    }


def usuario_logado():
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_connection()
    usuario = fetchone(conn, "SELECT id, nome, email, perfil FROM usuarios WHERE id = ?", (user_id,))
    conn.close()
    return usuario


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        usuario = usuario_logado()
        if usuario is None:
            return redirect(url_for("login"))
        if usuario["perfil"] != "admin":
            return redirect(url_for("index"))
        return view(*args, **kwargs)
    return wrapped


init_db()


@app.route("/")
def home():
    return redirect(url_for("index" if session.get("user_id") else "login"))


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "database": DB_ENGINE})


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("index"))

    erro = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""
        conn = get_connection()
        usuario = fetchone(conn, "SELECT id, senha_hash FROM usuarios WHERE email = ?", (email,))
        conn.close()

        if usuario is None or not check_password_hash(usuario["senha_hash"], senha):
            erro = "E-mail ou senha inválidos."
        else:
            session["user_id"] = usuario["id"]
            return redirect(url_for("index"))

    return render_template("login.html", erro=erro)


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if session.get("user_id"):
        return redirect(url_for("index"))

    erro = None
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""
        perfil = (request.form.get("perfil") or "aluno").strip().lower()

        if perfil not in {"aluno", "professor"}:
            erro = "Perfil inválido."
        elif not all([nome, email, senha]):
            erro = "Preencha todos os campos."
        elif len(senha) < 6:
            erro = "A senha precisa ter pelo menos 6 caracteres."
        else:
            conn = get_connection()
            existe = fetchone(conn, "SELECT id FROM usuarios WHERE email = ?", (email,))
            if existe:
                erro = "Já existe uma conta com esse e-mail."
                conn.close()
            else:
                if DB_ENGINE == "sqlite":
                    cursor = execute(
                        conn,
                        """
                        INSERT INTO usuarios (nome, email, senha_hash, perfil, criado_em)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (nome, email, generate_password_hash(senha), perfil, datetime.now(APP_TIMEZONE).isoformat(timespec="seconds")),
                    )
                    conn.commit()
                    session["user_id"] = cursor.lastrowid
                else:
                    with conn.cursor() as cur:
                        cur.execute(
                            adapt_query(
                                """
                                INSERT INTO usuarios (nome, email, senha_hash, perfil, criado_em)
                                VALUES (?, ?, ?, ?, ?)
                                RETURNING id
                                """
                            ),
                            (nome, email, generate_password_hash(senha), perfil, datetime.now(APP_TIMEZONE).isoformat(timespec="seconds")),
                        )
                        session["user_id"] = cur.fetchone()["id"]
                    conn.commit()
                conn.close()
                return redirect(url_for("index"))

    return render_template("register.html", erro=erro)


@app.route("/sair", methods=["POST"])
@login_required
def sair():
    session.clear()
    return redirect(url_for("login"))


@app.route("/app")
@login_required
def index():
    return render_template("index.html", usuario=usuario_logado(), **get_calendar_context())


@app.route("/reservas", methods=["GET"])
@login_required
def listar_reservas():
    conn = get_connection()
    reservas = fetchall(
        conn,
        """
        SELECT reservas.id, reservas.area, reservas.data, reservas.inicio, reservas.fim,
               COALESCE(usuarios.nome, reservas.nome) AS nome,
               usuarios.perfil,
               reservas.user_id
        FROM reservas
        LEFT JOIN usuarios ON usuarios.id = reservas.user_id
        ORDER BY reservas.data ASC, reservas.inicio ASC, reservas.area ASC
        """,
    )
    conn.close()
    return jsonify(rows_to_dicts(reservas))


@app.route("/usuarios", methods=["GET"])
@admin_required
def listar_usuarios():
    usuario = usuario_logado()
    conn = get_connection()
    usuarios = fetchall(
        conn,
        """
        SELECT id, nome, email, perfil, criado_em
        FROM usuarios
        ORDER BY CASE perfil WHEN 'admin' THEN 0 WHEN 'professor' THEN 1 ELSE 2 END, nome ASC
        """,
    )
    conn.close()
    return jsonify([{**row_to_dict(item), "is_current_user": item["id"] == usuario["id"]} for item in usuarios])


@app.route("/reservar", methods=["POST"])
@login_required
def reservar():
    dados = request.get_json(silent=True) or {}
    usuario = usuario_logado()
    area = (dados.get("area") or "").strip()
    data = (dados.get("data") or "").strip()
    inicio = (dados.get("inicio") or "").strip()
    fim = (dados.get("fim") or "").strip()

    if not all([area, data, inicio, fim]):
        return jsonify({"status": "erro", "msg": "Preencha todos os campos."}), 400
    if fim <= inicio:
        return jsonify({"status": "erro", "msg": "O horário final deve ser maior que o inicial."}), 400

    try:
        inicio_reserva = parse_reserva_datetime(data, inicio)
        fim_reserva = parse_reserva_datetime(data, fim)
    except ValueError:
        return jsonify({"status": "erro", "msg": "Data ou horário inválido."}), 400

    agora = datetime.now(APP_TIMEZONE)
    if inicio_reserva <= agora:
        return jsonify({"status": "erro", "msg": "Não é permitido reservar datas ou horários que já passaram."}), 400
    if fim_reserva <= agora:
        return jsonify({"status": "erro", "msg": "O fim da reserva também precisa estar no futuro."}), 400

    conn = get_connection()
    reservas_existentes = fetchall(
        conn,
        "SELECT inicio, fim FROM reservas WHERE area = ? AND data = ?",
        (area, data),
    )

    for reserva_existente in reservas_existentes:
        if horario_conflita(inicio, fim, reserva_existente["inicio"], reserva_existente["fim"]):
            conn.close()
            return jsonify({"status": "erro", "msg": "Já existe uma reserva nesse horário para essa área."}), 409

    execute(
        conn,
        "INSERT INTO reservas (nome, area, data, inicio, fim, user_id) VALUES (?, ?, ?, ?, ?, ?)",
        (usuario["nome"], area, data, inicio, fim, usuario["id"]),
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "msg": "Reserva criada com sucesso."})


@app.route("/excluir/<int:reserva_id>", methods=["DELETE"])
@login_required
def excluir(reserva_id):
    usuario = usuario_logado()
    conn = get_connection()
    reserva = fetchone(conn, "SELECT id, user_id FROM reservas WHERE id = ?", (reserva_id,))

    if reserva is None:
        conn.close()
        return jsonify({"status": "erro", "msg": "Reserva não encontrada."}), 404
    if usuario["perfil"] != "admin" and reserva["user_id"] != usuario["id"]:
        conn.close()
        return jsonify({"status": "erro", "msg": "Você só pode excluir suas próprias reservas."}), 403

    execute(conn, "DELETE FROM reservas WHERE id = ?", (reserva_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "msg": "Reserva excluída com sucesso."})


@app.route("/usuarios/<int:usuario_id>", methods=["DELETE"])
@admin_required
def excluir_usuario(usuario_id):
    usuario = usuario_logado()
    if usuario["id"] == usuario_id:
        return jsonify({"status": "erro", "msg": "O administrador não pode excluir a própria conta."}), 400

    conn = get_connection()
    alvo = fetchone(conn, "SELECT id, nome FROM usuarios WHERE id = ?", (usuario_id,))

    if alvo is None:
        conn.close()
        return jsonify({"status": "erro", "msg": "Usuário não encontrado."}), 404

    execute(conn, "UPDATE reservas SET user_id = NULL WHERE user_id = ?", (usuario_id,))
    execute(conn, "DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "msg": f"Cadastro de {alvo['nome']} removido com sucesso."})


if __name__ == "__main__":
    app.run(debug=True)
