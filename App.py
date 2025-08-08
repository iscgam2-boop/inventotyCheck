from flask import Flask, render_template, request, jsonify, session
import pandas as pd
import os
from werkzeug.utils import secure_filename
import json
import pickle
import uuid

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'  # Cambiar en producción

# Configuración
UPLOAD_FOLDER = 'uploads'
DATA_FOLDER = 'data'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

# Crear carpetas si no existen
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATA_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DATA_FOLDER'] = DATA_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_session_data_path(session_id):
    """Obtener la ruta del archivo de datos de la sesión"""
    return os.path.join(app.config['DATA_FOLDER'], f'session_{session_id}.pkl')

def save_session_data(session_id, data):
    """Guardar datos de la sesión en archivo"""
    try:
        filepath = get_session_data_path(session_id)
        with open(filepath, 'wb') as f:
            pickle.dump(data, f)
        return True
    except Exception as e:
        print(f"Error saving session data: {e}")
        return False

def load_session_data(session_id):
    """Cargar datos de la sesión desde archivo"""
    try:
        filepath = get_session_data_path(session_id)
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                return pickle.load(f)
        return None
    except Exception as e:
        print(f"Error loading session data: {e}")
        return None

def cleanup_session_data(session_id):
    """Limpiar archivo de datos de la sesión"""
    try:
        filepath = get_session_data_path(session_id)
        if os.path.exists(filepath):
            os.remove(filepath)
        return True
    except Exception as e:
        print(f"Error cleaning up session data: {e}")
        return False

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
            
            # Generar ID único para la sesión si no existe
            if 'session_id' not in session:
                session['session_id'] = str(uuid.uuid4())
            
            # Guardar datos en archivo temporal en lugar de sesión
            session_data = {
                'df': df,
                'scanned_items': [],
                'filename': filename
            }
            
            if save_session_data(session['session_id'], session_data):
                # Solo guardar metadata básica en la sesión
                session['has_data'] = True
                session['records_count'] = len(df)
                session['filename'] = filename
                
                # Limpiar archivo temporal
                os.remove(filepath)
                
                return jsonify({
                    'success': True,
                    'message': f'Archivo cargado correctamente. {len(df)} registros encontrados.',
                    'records_count': len(df),
                    'columns': list(df.columns),
                    'data': df.head(100).to_dict('records')  # Solo primeros 100 para la vista
                })
            else:
                return jsonify({'error': 'Error al guardar los datos'}), 500
        
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
        
        if not session.get('has_data') or 'session_id' not in session:
            return jsonify({'error': 'No hay datos cargados'}), 400
        
        # Cargar datos desde archivo
        session_data = load_session_data(session['session_id'])
        if not session_data:
            return jsonify({'error': 'Error al cargar los datos'}), 500
        
        df = session_data['df']
        scanned_items = session_data['scanned_items']
        
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
            
            # Actualizar datos en archivo
            session_data['scanned_items'] = scanned_items
            save_session_data(session['session_id'], session_data)
            
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
        if not session.get('has_data') or 'session_id' not in session:
            return jsonify({'error': 'No hay datos cargados'}), 400
        
        # Cargar datos desde archivo
        session_data = load_session_data(session['session_id'])
        if not session_data:
            return jsonify({'error': 'Error al cargar los datos'}), 500
        
        total_items = len(session_data['df'])
        scanned_items = len(session_data['scanned_items'])
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
        if not session.get('has_data') or 'session_id' not in session:
            return jsonify({'error': 'No hay datos cargados'}), 400
        
        # Cargar datos desde archivo
        session_data = load_session_data(session['session_id'])
        if not session_data:
            return jsonify({'error': 'Error al cargar los datos'}), 500
        
        df = session_data['df'].copy()
        scanned_items = session_data['scanned_items']
        
        # Agregar columna de estado
        df['Estado_Revision'] = df.index.map(lambda x: 'Escaneado' if x in scanned_items else 'Pendiente')
        
        # Convertir a formato JSON para descarga
        result = {
            'filename': session_data['filename'],
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
        # Limpiar archivos de datos si existen
        if 'session_id' in session:
            cleanup_session_data(session['session_id'])
        
        # Limpiar sesión
        session.clear()
        return jsonify({'success': True, 'message': 'Sesión reiniciada'})
    except Exception as e:
        return jsonify({'error': f'Error al reiniciar: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)