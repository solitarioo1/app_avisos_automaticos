from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def inicio():
    return render_template('inicio.html')

@app.route('/avisos')
def avisos():
    return "Avisos página"

@app.route('/mapas')
def mapas():
    return "Mapas página"

@app.route('/decisiones')
def decisiones():
    return "Decisiones página"

@app.route('/whatsapp')
def whatsapp():
    return "WhatsApp página"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)