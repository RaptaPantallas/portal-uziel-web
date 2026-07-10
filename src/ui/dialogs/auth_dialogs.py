import os
import random
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QPushButton, QLabel,
    QLineEdit, QFrame, QMessageBox, QApplication, QWidget, QStackedWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from src.database import ConexionBD

CARPETA_ACTIVOS = os.path.abspath("almacen_activos")

# =============================================================================
# ████████  DIÁLOGO DE LOGIN  ████████
# =============================================================================

class LoginDialog(QDialog):
    """Ventana modal de inicio de sesión con diseño profesional."""

    def __init__(self, bd=None):
        super().__init__()
        self.setWindowTitle("Iniciar Sesión — Importadora Uziel C.A.")
        self.setFixedSize(420, 500)
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0f172a, stop:1 #1e293b);
            }
        """)

        self.bd = bd or ConexionBD()
        self.usuario_autenticado = ""
        self.rol_autenticado = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Card central ──
        card = QFrame()
        card.setObjectName("card")
        card.setFixedSize(360, 420)
        cv = QVBoxLayout(card)
        cv.setContentsMargins(32, 28, 32, 28)
        cv.setSpacing(14)
        cv.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Logo
        ruta_logo = os.path.join(CARPETA_ACTIVOS, "Logo", "logo.png")
        if os.path.exists(ruta_logo):
            lbl_logo = QLabel()
            pixmap = QPixmap(ruta_logo)
            pixmap = pixmap.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            lbl_logo.setPixmap(pixmap)
            lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cv.addWidget(lbl_logo)

        # Título
        lbl_titulo = QLabel("IMPORTADORA UZIEL C.A.")
        lbl_titulo.setStyleSheet("font-size:18px; font-weight:700; color:#f8fafc;")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cv.addWidget(lbl_titulo)

        lbl_sub = QLabel("Sistema de Información — Dashboard")
        lbl_sub.setStyleSheet("font-size:12px; color:#94a3b8;")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cv.addWidget(lbl_sub)

        cv.addSpacing(12)

        input_style = """
            QLineEdit {
                border: 1.5px solid #334155; border-radius: 8px;
                padding: 0 12px; font-size: 14px; background: #0f172a;
                color: #f8fafc;
            }
            QLineEdit:focus { border-color: #3b82f6; background: #1e293b; }
            QLineEdit::placeholder { color: #64748b; }
        """

        # Campo usuario
        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("Usuario")
        self.input_user.setStyleSheet(input_style)
        self.input_user.setFixedHeight(42)
        cv.addWidget(self.input_user)

        # Campo contraseña
        lay_pass = QHBoxLayout()
        lay_pass.setSpacing(6)
        
        self.input_pass = QLineEdit()
        self.input_pass.setPlaceholderText("Contraseña")
        self.input_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pass.setStyleSheet(input_style)
        self.input_pass.setFixedHeight(42)
        self.input_pass.returnPressed.connect(self._iniciar_sesion)
        lay_pass.addWidget(self.input_pass)
        
        self.btn_toggle_pass = QPushButton("Ver")
        self.btn_toggle_pass.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_pass.setFixedSize(55, 42)
        self.btn_toggle_pass.setStyleSheet("""
            QPushButton {
                background: #0f172a; color: #94a3b8; border: 1.5px solid #334155;
                border-radius: 8px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background: #1e293b; color: #f8fafc; border-color: #3b82f6; }
        """)
        self.btn_toggle_pass.clicked.connect(self._toggle_password_visibility)
        lay_pass.addWidget(self.btn_toggle_pass)
        
        cv.addLayout(lay_pass)

        # Forgot password label
        self.lbl_forgot = QLabel("¿Olvidó su contraseña?")
        self.lbl_forgot.setStyleSheet("color:#60a5fa; font-size:11px; text-decoration: underline;")
        self.lbl_forgot.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_forgot.mousePressEvent = lambda event: self._mostrar_forgot_password()
        cv.addWidget(self.lbl_forgot)
        cv.addSpacing(4)

        # Mensaje de error
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color:#ef4444; font-size:11px;")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cv.addWidget(self.lbl_error)

        # Botón login
        btn_login = QPushButton("  Iniciar Sesión  ")
        btn_login.setStyleSheet("""
            QPushButton {
                background: #2563eb; color: white; border: none;
                border-radius: 8px; padding: 12px; font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover { background: #1d4ed8; }
            QPushButton:pressed { background: #1e40af; }
        """)
        btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_login.clicked.connect(self._iniciar_sesion)
        cv.addWidget(btn_login)

        # Pie
        lbl_pie = QLabel("v1.0 — Todos los derechos reservados")
        lbl_pie.setStyleSheet("color:#94a3b8; font-size:10px;")
        lbl_pie.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cv.addWidget(lbl_pie)

        # Centrar card
        wrapper = QHBoxLayout()
        wrapper.addStretch()
        wrapper.addWidget(card)
        wrapper.addStretch()
        root.addStretch()
        root.addLayout(wrapper)
        root.addStretch()

        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0f172a, stop:1 #1e293b);
            }
            QFrame#card {
                background: #1e293b;
                border: 1.5px solid #334155;
                border-radius: 16px;
            }
        """)

    def _toggle_password_visibility(self):
        if self.input_pass.echoMode() == QLineEdit.EchoMode.Password:
            self.input_pass.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_pass.setText("Ocultar")
        else:
            self.input_pass.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_pass.setText("Ver")

    def _mostrar_forgot_password(self):
        dlg = ForgotPasswordDialog(self.bd)
        dlg.exec()

    def _iniciar_sesion(self):
        usuario = self.input_user.text().strip()
        contrasena = self.input_pass.text()

        if not usuario or not contrasena:
            self.lbl_error.setText("Ingresa usuario y contraseña.")
            return

        # Verificar si la cuenta está bloqueada
        if self.bd.usuario_esta_bloqueado(usuario):
            self.lbl_error.setText(
                " Cuenta bloqueada por demasiados intentos fallidos.\n"
                "Contacta al administrador para desbloquearla."
            )
            self.lbl_error.setStyleSheet("color:#ef4444; font-size:11px;")
            self.input_pass.clear()
            self.input_pass.setFocus()
            return

        resultado = self.bd.verificar_login(usuario, contrasena)
        if resultado:
            self.usuario_autenticado = resultado[0]
            self.rol_autenticado = resultado[1]
            self.accept()
        else:
            intentos = self.bd.obtener_intentos_fallidos(usuario)
            restantes = max(0, self.bd.MAX_INTENTOS - intentos)
            if restantes > 0:
                self.lbl_error.setText(
                    f" Usuario o contraseña incorrectos. "
                    f"Te quedan {restantes} intento(s)."
                )
            else:
                self.lbl_error.setText(
                    " Cuenta bloqueada por demasiados intentos fallidos.\n"
                    "Contacta al administrador para desbloquearla."
                )
            self.input_pass.clear()
            self.input_pass.setFocus()


# =============================================================================
# ████████  CAMBIO DE CONTRASEÑA  ████████
# =============================================================================

class UserPasswordDialog(QDialog):
    """Diálogo para cambiar la contraseña de un usuario."""

    def exec(self):
        if hasattr(self, '_ignorar_exec') and self._ignorar_exec:
            return QDialog.DialogCode.Rejected
        return super().exec()

    def __init__(self, bd, usuario_actual, es_superadmin, username):
        super().__init__()
        self.bd = bd
        self.usuario_actual = usuario_actual
        self.es_superadmin = es_superadmin
        self.username = username

        # Validar seguridad antes de inicializar interfaz
        if self.bd.es_superadmin(username) and not self.es_superadmin:
            QMessageBox.critical(self, "Acceso Denegado", "Solo el superadmin puede cambiar la contraseña de otro superadmin.")
            self._ignorar_exec = True
            self.reject()
            return

        self.setWindowTitle(f"Contraseña de '{username}'")
        self.setFixedSize(380, 200)
        self.setStyleSheet("QDialog { background: #f8fafc; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        lbl = QLabel(f" Cambiar contraseña de '{username}'")
        lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #0f172a;")
        root.addWidget(lbl)

        fg = QFormLayout()
        fg.setSpacing(8)
        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pass.setPlaceholderText("Nueva contraseña")
        self.input_pass.setStyleSheet("border:1.5px solid #e2e8f0;border-radius:6px;padding:8px 10px;font-size:13px;")
        fg.addRow("Contraseña:", self.input_pass)

        self.input_confirm = QLineEdit()
        self.input_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_confirm.setPlaceholderText("Repite la contraseña")
        self.input_confirm.setStyleSheet("border:1.5px solid #e2e8f0;border-radius:6px;padding:8px 10px;font-size:13px;")
        fg.addRow("Confirmar:", self.input_confirm)
        root.addLayout(fg)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet("background:#e2e8f0;color:#1e293b;padding:8px 20px;border-radius:6px;font-weight:600;")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("Actualizar")
        btn_save.setStyleSheet("background:#2563eb;color:#fff;padding:8px 20px;border-radius:6px;font-weight:600;")
        btn_save.clicked.connect(self._guardar)
        btn_box.addWidget(btn_save)
        root.addLayout(btn_box)

    def _guardar(self):
        p1 = self.input_pass.text()
        p2 = self.input_confirm.text()
        if not p1 or not p2:
            QMessageBox.warning(self, "Error", "Ambos campos son obligatorios.")
            return
        if p1 != p2:
            QMessageBox.warning(self, "Error", "Las contraseñas no coinciden.")
            return

        # Validar seguridad antes de guardar
        if self.bd.es_superadmin(self.username) and not self.es_superadmin:
            QMessageBox.critical(self, "Acceso Denegado", "Solo el superadmin puede cambiar la contraseña de otro superadmin.")
            self.reject()
            return

        ok = self.bd.actualizar_password_usuario(self.username, p1)
        if ok:
            QMessageBox.information(self, "Éxito", f"Contraseña de '{self.username}' actualizada.")
            self.accept()
        else:
            QMessageBox.warning(self, "Error", f"No se pudo cambiar la contraseña.")


# =============================================================================
# ████████  RECUPERAR CONTRASEÑA  ████████
# =============================================================================

class ForgotPasswordDialog(QDialog):
    """Diálogo para recuperar la contraseña mediante email (Fase 1 y Fase 2)."""
    def __init__(self, bd):
        super().__init__()
        self.bd = bd
        self.setWindowTitle("Recuperar Contraseña")
        self.setFixedSize(380, 280)
        self.setStyleSheet("""
            QDialog { background: #f8fafc; }
            QLabel { color: #0f172a; font-size: 13px; }
            QLineEdit {
                border: 1.5px solid #cbd5e1;
                border-radius: 6px;
                padding: 8px 10px;
                font-size: 13px;
                background: #ffffff;
                color: #0f172a;
            }
            QLineEdit:focus { border-color: #2563eb; }
            QPushButton {
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
            }
        """)
        
        self.username = ""
        
        self.layout_principal = QVBoxLayout(self)
        self.layout_principal.setContentsMargins(24, 20, 24, 20)
        self.layout_principal.setSpacing(14)
        
        self.stack = QStackedWidget()
        
        # --- PASO 1 ---
        self.widget_paso1 = QWidget()
        lay1 = QVBoxLayout(self.widget_paso1)
        lay1.setContentsMargins(0, 0, 0, 0)
        lay1.setSpacing(12)
        
        lbl_info1 = QLabel("Ingresa tu usuario o correo electrónico registrado para recibir un código de recuperación.")
        lbl_info1.setWordWrap(True)
        lbl_info1.setStyleSheet("color: #475569; font-size: 12px; line-height: 1.4;")
        lay1.addWidget(lbl_info1)
        
        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("Usuario o Correo")
        lay1.addWidget(self.input_user)
        
        btn_box1 = QHBoxLayout()
        btn_box1.addStretch()
        btn_cancel1 = QPushButton("Cancelar")
        btn_cancel1.setStyleSheet("background: #e2e8f0; color: #1e293b; border: none;")
        btn_cancel1.clicked.connect(self.reject)
        btn_box1.addWidget(btn_cancel1)
        
        self.btn_send1 = QPushButton("Enviar Código")
        self.btn_send1.setStyleSheet("background: #2563eb; color: #ffffff; border: none;")
        self.btn_send1.clicked.connect(self._solicitar_codigo)
        btn_box1.addWidget(self.btn_send1)
        lay1.addLayout(btn_box1)
        
        # --- PASO 2 ---
        self.widget_paso2 = QWidget()
        lay2 = QVBoxLayout(self.widget_paso2)
        lay2.setContentsMargins(0, 0, 0, 0)
        lay2.setSpacing(10)
        
        self.lbl_info2 = QLabel("Se ha enviado un código de recuperación a tu correo. Por favor, ingresa los datos a continuación.")
        self.lbl_info2.setWordWrap(True)
        self.lbl_info2.setStyleSheet("color: #0369a1; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 6px; padding: 8px; font-size: 11px;")
        lay2.addWidget(self.lbl_info2)
        
        self.input_code = QLineEdit()
        self.input_code.setPlaceholderText("Código de 6 dígitos")
        self.input_code.setMaxLength(6)
        lay2.addWidget(self.input_code)
        
        self.input_new_pass = QLineEdit()
        self.input_new_pass.setPlaceholderText("Nueva contraseña (mín. 4 caracteres)")
        self.input_new_pass.setEchoMode(QLineEdit.EchoMode.Password)
        lay2.addWidget(self.input_new_pass)
        
        self.input_confirm_pass = QLineEdit()
        self.input_confirm_pass.setPlaceholderText("Confirmar contraseña")
        self.input_confirm_pass.setEchoMode(QLineEdit.EchoMode.Password)
        lay2.addWidget(self.input_confirm_pass)
        
        btn_box2 = QHBoxLayout()
        btn_box2.addStretch()
        btn_back2 = QPushButton("Atrás")
        btn_back2.setStyleSheet("background: #e2e8f0; color: #1e293b; border: none;")
        btn_back2.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        btn_box2.addWidget(btn_back2)
        
        btn_save2 = QPushButton("Restablecer")
        btn_save2.setStyleSheet("background: #22c55e; color: #ffffff; border: none;")
        btn_save2.clicked.connect(self._restablecer_password)
        btn_box2.addWidget(btn_save2)
        lay2.addLayout(btn_box2)
        
        self.stack.addWidget(self.widget_paso1)
        self.stack.addWidget(self.widget_paso2)
        self.layout_principal.addWidget(self.stack)

    def _solicitar_codigo(self):
        identificador = self.input_user.text().strip()
        if not identificador:
            QMessageBox.warning(self, "Error", "Ingresa tu usuario o correo electrónico.")
            return
            
        self.btn_send1.setEnabled(False)
        self.btn_send1.setText("Enviando...")
        QApplication.processEvents()
        
        try:
            username, email = self.bd.obtener_datos_recuperacion(identificador)
            if not username or not email:
                QMessageBox.warning(self, "Error", "No se encontró un correo electrónico asociado a esa cuenta.\nContacta al administrador.")
                self.btn_send1.setEnabled(True)
                self.btn_send1.setText("Enviar Código")
                return
                
            codigo = str(random.randint(100000, 999999))
            
            if self.bd.guardar_codigo_recuperacion(username, codigo):
                exito, msg = self.bd.enviar_correo_recuperacion(email, codigo)
                if exito:
                    self.username = username
                    self.lbl_info2.setText(f"Se envió un código a {email}. Revisa tu bandeja de entrada.")
                    self.stack.setCurrentIndex(1)
                else:
                    QMessageBox.warning(self, "Error", f"No se pudo enviar el correo: {msg}")
            else:
                QMessageBox.warning(self, "Error", "Error interno al generar el código.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Ocurrió un error inesperado: {e}")
            
        self.btn_send1.setEnabled(True)
        self.btn_send1.setText("Enviar Código")

    def _restablecer_password(self):
        codigo = self.input_code.text().strip()
        pwd = self.input_new_pass.text()
        confirm = self.input_confirm_pass.text()
        
        if not codigo or not pwd or not confirm:
            QMessageBox.warning(self, "Error", "Todos los campos son obligatorios.")
            return
            
        if pwd != confirm:
            QMessageBox.warning(self, "Error", "Las contraseñas no coinciden.")
            return
            
        if len(pwd) < 4:
            QMessageBox.warning(self, "Error", "La contraseña debe tener al menos 4 caracteres.")
            return
            
        if not self.bd.verificar_codigo_recuperacion(self.username, codigo):
            QMessageBox.warning(self, "Error", "Código de recuperación inválido o expirado.")
            return
            
        if self.bd.cambiar_password_con_codigo(self.username, codigo, pwd):
            QMessageBox.information(self, "Éxito", "Contraseña restablecida correctamente. Ahora puedes iniciar sesión.")
            self.accept()
        else:
            QMessageBox.warning(self, "Error", "Error al actualizar la contraseña en el sistema.")


# =============================================================================
# ████████  CONFIRMACIÓN DE SEGURIDAD  ████████
# =============================================================================

class ReAuthDialog(QDialog):
    """
    Diálogo modal que pide la contraseña actual para autorizar
    operaciones sensibles.
    """

    def __init__(self, bd, usuario_actual, operacion="realizar esta operación", parent=None):
        super().__init__(parent)
        self.bd = bd
        self.usuario_actual = usuario_actual
        self.autorizado = False

        self.setWindowTitle("Confirmación de seguridad")
        self.setFixedSize(380, 220)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background: #ffffff;
                border-radius: 12px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        icono = QLabel("  ")
        icono.setStyleSheet("font-size: 32px;")
        icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(icono)

        lbl_msg = QLabel(f"Para {operacion}, ingresa tu contraseña actual:")
        lbl_msg.setStyleSheet("font-size: 13px; color: #1e293b;")
        lbl_msg.setWordWrap(True)
        lbl_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(lbl_msg)

        self.input_pass = QLineEdit()
        self.input_pass.setPlaceholderText("Tu contraseña")
        self.input_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pass.setStyleSheet("""
            QLineEdit {
                border: 1.5px solid #e2e8f0; border-radius: 8px;
                padding: 10px 12px; font-size: 14px; background: #f8fafc;
                color: #1e293b;
            }
            QLineEdit:focus { border-color: #2563eb; background: #ffffff; }
        """)
        self.input_pass.returnPressed.connect(self._verificar)
        root.addWidget(self.input_pass)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #ef4444; font-size: 11px;")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.lbl_error)

        fila_btn = QHBoxLayout()
        fila_btn.addStretch()

        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setStyleSheet(
            "background: #ffffff; color: #64748b; border: 1.5px solid #e2e8f0; "
            "border-radius: 8px; padding: 8px 18px; font-size: 13px; font-weight: 600;"
        )
        btn_cancelar.clicked.connect(self.reject)
        fila_btn.addWidget(btn_cancelar)

        btn_confirmar = QPushButton("Confirmar")
        btn_confirmar.setStyleSheet(
            "background: #2563eb; color: white; border: none; "
            "border-radius: 8px; padding: 8px 18px; font-size: 13px; font-weight: 600;"
        )
        btn_confirmar.clicked.connect(self._verificar)
        fila_btn.addWidget(btn_confirmar)

        root.addLayout(fila_btn)

    def _verificar(self):
        password = self.input_pass.text()
        if not password:
            self.lbl_error.setText("Ingresa tu contraseña.")
            return
        resultado = self.bd.verificar_login(self.usuario_actual, password)
        if resultado:
            self.autorizado = True
            self.accept()
        else:
            self.lbl_error.setText("Contraseña incorrecta.")
            self.input_pass.clear()
            self.input_pass.setFocus()
