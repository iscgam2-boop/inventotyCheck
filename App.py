from flask import Flask, render_template, request, jsonify, session
import pandas as pd
import os
from werkzeug.utils import secure_filename
import json

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'  # Cambiar en producción

# Configuración
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

# Crear carpeta de uploads si no existe
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No se seleccionó archivo'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No se seleccionó archivo'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Leer el archivo Excel
            df = pd.read_excel(filepath)
            
            # Guardar datos en la sesión (convertir a JSON)
            session['df_data'] = df.to_dict('records')
            session['df_columns'] = list(df.columns)
            session['scanned_items'] = []
            session['filename'] = filename
            
            # Limpiar archivo temporal
            os.remove(filepath)
            
            return jsonify({
                'success': True,
                'message': f'Archivo cargado correctamente. {len(df)} registros encontrados.',
                'records_count': len(df),
                'columns': list(df.columns),
                'data': df.to_dict('records')[:100]  # Limitar a 100 registros para la vista inicial
            })
        
        return jsonify({'error': 'Tipo de archivo no permitido'}), 400
        
    except Exception as e:
        return jsonify({'error': f'Error al procesar archivo: {str(e)}'}), 500

@app.route('/search', methods=['POST'])
def search_barcode():
    try:
        data = request.get_json()
        barcode = data.get('barcode', '').strip()
        
        if not barcode:
            return jsonify({'error': 'Código de barras vacío'}), 400
        
        if 'df_data' not in session:
            return jsonify({'error': 'No hay datos cargados'}), 400
        
        # Reconstruir DataFrame desde la sesión
        df = pd.DataFrame(session['df_data'])
        scanned_items = session.get('scanned_items', [])
        
        # Buscar el código en todas las columnas
        found_indices = []
        
        for col in df.columns:
            col_str = df[col].astype(str)
            matches = col_str == barcode
            if matches.any():
                matched_indices = df[matches].index.tolist()
                found_indices.extend(matched_indices)
        
        if found_indices:
            # Agregar índices encontrados a items escaneados
            new_scanned = []
            for idx in found_indices:
                if idx not in scanned_items:
                    scanned_items.append(idx)
                    new_scanned.append(idx)
            
            session['scanned_items'] = scanned_items
            
            return jsonify({
                'success': True,
                'found': True,
                'message': f'Código encontrado en {len(found_indices)} registro(s)',
                'matched_indices': found_indices,
                'new_scanned': new_scanned,
                'total_scanned': len(scanned_items)
            })
        else:
            return jsonify({
                'success': True,
                'found': False,
                'message': f'El código "{barcode}" no se encontró en el inventario'
            })
            
    except Exception as e:
        return jsonify({'error': f'Error en la búsqueda: {str(e)}'}), 500

@app.route('/stats')
def get_stats():
    try:
        if 'df_data' not in session:
            return jsonify({'error': 'No hay datos cargados'}), 400
        
        total_items = len(session['df_data'])
        scanned_items = len(session.get('scanned_items', []))
        pending_items = total_items - scanned_items
        progress = (scanned_items / total_items * 100) if total_items > 0 else 0
        
        return jsonify({
            'total_items': total_items,
            'scanned_items': scanned_items,
            'pending_items': pending_items,
            'progress': round(progress, 2)
        })
        
    except Exception as e:
        return jsonify({'error': f'Error al obtener estadísticas: {str(e)}'}), 500

@app.route('/export')
def export_results():
    try:
        if 'df_data' not in session:
            return jsonify({'error': 'No hay datos cargados'}), 400
        
        df = pd.DataFrame(session['df_data'])
        scanned_items = session.get('scanned_items', [])
        
        # Agregar columna de estado
        df['Estado_Revision'] = df.index.map(lambda x: 'Escaneado' if x in scanned_items else 'Pendiente')
        
        # Convertir a formato JSON para descarga
        result = {
            'filename': session.get('filename', 'inventario'),
            'data': df.to_dict('records'),
            'summary': {
                'total': len(df),
                'escaneados': len(scanned_items),
                'pendientes': len(df) - len(scanned_items)
            }
        }
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'Error al exportar: {str(e)}'}), 500

@app.route('/reset')
def reset_session():
    try:
        session.clear()
        return jsonify({'success': True, 'message': 'Sesión reiniciada'})
    except Exception as e:
        return jsonify({'error': f'Error al reiniciar: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)