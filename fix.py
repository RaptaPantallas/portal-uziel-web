import sys

path = 'g:/Mi unidad/PROGRAMA/uziel_dashboard/main.py'
content = open(path, 'r', encoding='utf-8').read()

target = """        validador_numeros = QRegularExpressionValidator(QRegularExpression(r"^[0-9]+$"))

        self.input_rif.setValidator(validador_numeros)
        layout_tel.setContentsMargins(0, 0, 0, 0)
        
        self.combo_prefijo_tel = QComboBox(); self.combo_prefijo_tel.setView(QListView())
        self.combo_prefijo_tel.addItems(["0414", "0424", "0412", "0416", "0426", "0212", "0422"])"""

replacement = """        validador_numeros = QRegularExpressionValidator(QRegularExpression(r"^[0-9]+$"))

        # --- COLUMNA IZQUIERDA: Identificación ---
        lbl_identificacion = self._label_seccion("DATOS DE IDENTIFICACIÓN")
        grid.addWidget(lbl_identificacion, 0, 0, 1, 2)

        grid.addWidget(QLabel("RIF / Cédula:"), 1, 0)
        layout_rif = QHBoxLayout()
        layout_rif.setSpacing(4)
        layout_rif.setContentsMargins(0, 0, 0, 0)
        
        self.combo_tipo_rif = QComboBox(); self.combo_tipo_rif.setView(QListView())
        self.combo_tipo_rif.addItems(["V - Venezolano", "J - Jurídico", "E - Extranjero", "G - Gobierno", "P - Pasaporte"])
        self.combo_tipo_rif.setFixedWidth(160)
        
        self.input_rif = QLineEdit()
        self.input_rif.setPlaceholderText("Ej: 123456789")
        self.input_rif.setMaxLength(9)
        self.input_rif.setValidator(validador_numeros)
        
        layout_rif.addWidget(self.combo_tipo_rif)
        layout_rif.addWidget(self.input_rif)
        grid.addLayout(layout_rif, 1, 1)

        grid.addWidget(QLabel("Empresa / Nombre:"), 2, 0)
        self.input_nombre = QLineEdit()
        self.input_nombre.setPlaceholderText("Nombre legal o de la persona")
        grid.addWidget(self.input_nombre, 2, 1)

        # --- COLUMNA DERECHA: Contacto ---
        lbl_contacto = self._label_seccion("DATOS DE CONTACTO")
        grid.addWidget(lbl_contacto, 0, 2, 1, 2)

        grid.addWidget(QLabel("Teléfono:"), 1, 2)
        layout_tel = QHBoxLayout()
        layout_tel.setSpacing(4)
        layout_tel.setContentsMargins(0, 0, 0, 0)
        
        self.combo_prefijo_tel = QComboBox(); self.combo_prefijo_tel.setView(QListView())
        self.combo_prefijo_tel.addItems(["0414", "0424", "0412", "0416", "0426", "0212", "0422"])"""

if target in content:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.replace(target, replacement))
    print("FIXED SUCCESSFULLY")
else:
    print("TARGET NOT FOUND IN FILE")
    # try to find a partial match
    lines = content.split('\\n')
    for i, line in enumerate(lines):
        if "validador_numeros = QRegularExpressionValidator" in line:
            print("Found validador_numeros at line", i)
            print('\\n'.join(lines[i:i+20]))
            break
