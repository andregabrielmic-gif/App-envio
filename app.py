import os
import base64
import io
import pytz
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from werkzeug.utils import secure_filename

# ---------- CONFIGURAÇÃO ----------
app = Flask(__name__)
app.secret_key = 'chave_secreta'

# Configuração do banco de dados
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chamados.db')

# Configuração da pasta de uploads
UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)

# ---------- FILTRO PARA FORMATAR DATA LOCAL NO HTML ----------
@app.template_filter('localdatetime')
def format_datetime_local(value):
    if value is None:
        return ""
    utc_tz = pytz.timezone('UTC')
    local_tz = pytz.timezone('America/Sao_Paulo')
    local_dt = utc_tz.localize(value).astimezone(local_tz)
    return local_dt.strftime('%d/%m/%Y %H:%M')

# ---------- MODELO DO BANCO DE DADOS ----------
class Chamado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    responsavel_envio = db.Column(db.String(100))
    checklist = db.Column(db.String(500))
    fotos = db.Column(db.String(500))
    assinatura = db.Column(db.String(200))
    observacoes_envio = db.Column(db.Text)
    data_envio = db.Column(db.DateTime, default=db.func.now())
    status = db.Column(db.String(50), default='Em andamento')
    data_retorno = db.Column(db.String(50))

# ---------- ROTA PARA SERVIR ARQUIVOS ----------
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Em app.py, substitua apenas a função index() por esta

# ---------- ROTA PRINCIPAL (COM CÓDIGO DE DEBUG) ----------
@app.route('/')
def index():
    # --- INÍCIO DO CÓDIGO DE DEBUG ---
    import os
    print("-------------------------------------------")
    print("--- INICIANDO DEBUG DA ROTA INDEX ---")
    print(f"Diretório de Trabalho Atual (CWD): {os.getcwd()}")
    print(f"Caminho Raiz do App (app.root_path): {app.root_path}")
    print("-------------------------------------------")
    # --- FIM DO CÓDIGO DE DEBUG ---

    chamados = Chamado.query.order_by(Chamado.id.desc()).all()
    return render_template('index.html', chamados=chamados)

# ---------- CRIAR NOVO CHAMADO ----------
@app.route('/novo', methods=['GET', 'POST'])
def novo():
    if request.method == 'POST':
        responsavel = request.form['responsavel_envio']
        observacoes = request.form['observacoes_envio']
        checklist_items = request.form.getlist('checklist')
        checklist_str = '; '.join(checklist_items)
        fotos_salvas = []
        fotos = request.files.getlist('fotos')
        for foto in fotos:
            if foto and foto.filename != '':
                filename = secure_filename(foto.filename)
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                unique_filename = f"{timestamp}_{filename}"
                foto.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                fotos_salvas.append(unique_filename)
        fotos_str = ';'.join(fotos_salvas)
        assinatura_filename = None
        assinatura_base64 = request.form['assinatura_base64']
        if "data:image/png;base64," in assinatura_base64:
            img_data = assinatura_base64.split(',')[1]
            assinatura_filename = f"assinatura_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
            with open(os.path.join(app.config['UPLOAD_FOLDER'], assinatura_filename), "wb") as fh:
                fh.write(base64.b64decode(img_data))
        novo_chamado = Chamado(
            responsavel_envio=responsavel,
            checklist=checklist_str,
            fotos=fotos_str,
            assinatura=assinatura_filename,
            observacoes_envio=observacoes
        )
        db.session.add(novo_chamado)
        db.session.commit()
        flash('Chamado criado com sucesso!')
        return redirect(url_for('index'))
    return render_template('novo.html')

# ---------- ROTA DE EDIÇÃO ----------
@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    chamado = Chamado.query.get_or_404(id)
    if request.method == 'POST':
        chamado.status = request.form['status']
        chamado.data_retorno = request.form['data_retorno']
        novas_fotos = request.files.getlist('novas_fotos')
        fotos_novas_salvas = []
        for foto in novas_fotos:
            if foto and foto.filename != '':
                filename = secure_filename(foto.filename)
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                unique_filename = f"{timestamp}_{filename}"
                foto.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                fotos_novas_salvas.append(unique_filename)
        if fotos_novas_salvas:
            fotos_atuais = chamado.fotos.split(';') if chamado.fotos else []
            fotos_totais = list(filter(None, fotos_atuais)) + fotos_novas_salvas
            chamado.fotos = ';'.join(fotos_totais)
        db.session.commit()
        flash('Chamado atualizado com sucesso!')
        return redirect(url_for('index'))
    return render_template('editar.html', chamado=chamado)

# ---------- ROTA DE EXCLUSÃO ----------
@app.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    chamado = Chamado.query.get_or_404(id)
    if chamado.fotos:
        fotos_lista = chamado.fotos.split(';')
        for foto_filename in fotos_lista:
            if foto_filename:
                foto_path = os.path.join(app.config['UPLOAD_FOLDER'], foto_filename)
                if os.path.exists(foto_path):
                    os.remove(foto_path)
    if chamado.assinatura:
        assinatura_path = os.path.join(app.config['UPLOAD_FOLDER'], chamado.assinatura)
        if os.path.exists(assinatura_path):
            os.remove(assinatura_path)
    db.session.delete(chamado)
    db.session.commit()
    flash('Chamado excluído com sucesso!', 'success')
    return redirect(url_for('index'))

# ---------- GERAR PDF (VERSÃO COM IMAGENS) ----------
@app.route('/gerar_pdf/<int:id>')
def gerar_pdf(id):
    chamado = Chamado.query.get_or_404(id)
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer)
    p.setTitle(f"Chamado_{chamado.id}")
    x_margin = 70
    y_position = 780
    line_height = 20
    bottom_margin = 50
    p.setFont("Helvetica-Bold", 16)
    p.drawString(x_margin, y_position, f"Relatório do Chamado ID: {chamado.id}")
    y_position -= (line_height * 2)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(x_margin, y_position, "Responsável pelo Envio:")
    p.setFont("Helvetica", 12)
    p.drawString(x_margin + 150, y_position, chamado.responsavel_envio)
    y_position -= line_height
    p.setFont("Helvetica-Bold", 12)
    p.drawString(x_margin, y_position, "Data de Envio:")
    p.setFont("Helvetica", 12)
    p.drawString(x_margin + 150, y_position, chamado.data_envio.strftime('%d/%m/%Y %H:%M:%S'))
    y_position -= (line_height * 2)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(x_margin, y_position, "Checklist Verificado:")
    y_position -= line_height
    p.setFont("Helvetica", 10)
    checklist_items = chamado.checklist.split('; ')
    for item in checklist_items:
        if y_position < bottom_margin: p.showPage(); y_position = 780
        p.drawString(x_margin + 15, y_position, f"- {item}")
        y_position -= 15
    y_position -= line_height
    p.setFont("Helvetica-Bold", 12)
    if y_position < bottom_margin: p.showPage(); y_position = 780
    p.drawString(x_margin, y_position, "Observações:")
    p.setFont("Helvetica", 10)
    p.drawString(x_margin + 15, y_position - 15, chamado.observacoes_envio or "Nenhuma observação.")
    y_position -= (line_height * 2)
    if chamado.assinatura:
        p.setFont("Helvetica-Bold", 12)
        if y_position < bottom_margin + 100: p.showPage(); y_position = 780
        p.drawString(x_margin, y_position, "Assinatura do Responsável:")
        y_position -= 110
        assinatura_path = os.path.join(app.config['UPLOAD_FOLDER'], chamado.assinatura)
        if os.path.exists(assinatura_path):
            p.drawImage(assinatura_path, x_margin, y_position, width=200, height=100, preserveAspectRatio=True)
        y_position -= line_height
    if chamado.fotos:
        if y_position < bottom_margin + 150: p.showPage(); y_position = 780
        p.setFont("Helvetica-Bold", 16)
        p.drawString(x_margin, y_position, "Fotos de Evidência")
        y_position -= line_height
        fotos_lista = chamado.fotos.split(';')
        for foto_filename in fotos_lista:
            if foto_filename:
                foto_path = os.path.join(app.config['UPLOAD_FOLDER'], foto_filename)
                if os.path.exists(foto_path):
                    max_width = 450
                    img_reader = ImageReader(foto_path)
                    img_width, img_height = img_reader.getSize()
                    aspect_ratio = img_height / float(img_width)
                    final_height = max_width * aspect_ratio
                    if y_position < final_height + bottom_margin:
                        p.showPage()
                        y_position = 780
                    p.setFont("Helvetica-Oblique", 10)
                    p.drawString(x_margin, y_position, foto_filename)
                    y_position -= (line_height - 5)
                    p.drawImage(foto_path, x_margin, y_position - final_height, width=max_width, height=final_height, preserveAspectRatio=True)
                    y_position -= (final_height + line_height)
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f'chamado_{chamado.id}.pdf', mimetype='application/pdf')

# ---------- EXECUÇÃO ----------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)