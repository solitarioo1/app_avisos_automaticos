INSERT INTO entidades (nombre) VALUES
('FINANCIERA CONFIANZA'),
('AGROBANCO'),
('CAJA ICA'),
('CAJA PIURA'),
('CAJA AREQUIPA'),
('CAJA HUANCAYO'),
('CAJA CUSCO'),
('CAJA PAITA'),
('CAJA LOS ANDES'),
('FINANCIERA QAPAQ'),
('FINANCIERA COOPAC'), 
('CAJA RURAL');

-- INSERTAR CULTIVOS
INSERT INTO tabla_cultivos (nombre) VALUES 
('ACEITUNA'), ('ACHIOTE'), ('AJÍ'), ('AJO'), ('ALCACHOFA'), 
('ALFALFA'), ('ALGODÓN'), ('ALMENDRA'), ('ARÁNDANO'), ('ARROZ'), 
('ARVEJA'), ('AVENA'), ('CACAO'), ('CAFÉ'), ('CAMOTE'), 
('CAÑA DE AZÚCAR'), ('CAÑIHUA'), ('CAPULÍ'), ('CASTAÑA'), ('CEBADA'), 
('CEBOLLA'), ('CEREZA'), ('CHIRIMOYA'), ('CIRUELA'), ('CÍTRICOS'), 
('COCO'), ('COLIFLOR'), ('DURAZNO'), ('ESPÁRRAGO'), ('ESPINACA'), 
('FRÍJOL'), ('FRESÓN'), ('GARBANZO'), ('GRANADA'), ('GRANADILLA'), 
('GUANÁBANA'), ('GUAYABA'), ('HABA'), ('HIGOS'), ('KIWICHA'), 
('LENTEJA'), ('LIMÓN'), ('LÚCUMA'), ('MAÍZ AMARILLO DURO'), ('MAÍZ AMILÁCEO'), 
('MAÍZ CHALA'), ('MANDARINA'), ('MANGO'), ('MANZANA'), ('MARACUYÁ'), 
('MASHUA'), ('MELÓN'), ('MEMBRILLO'), ('NARANJA'), ('NECTARINA'), 
('NÍSPERO'), ('OCA'), ('OLLUCO'), ('OLIVO'), ('PALLAR'), 
('PALTO'), ('PAPA'), ('PÁPRIKA'), ('PASTOS CULTIVADOS'), ('PEPINO'), 
('PERA'), ('PIMIENTO'), ('PIÑA'), ('PLÁTANO'), ('QUINUA'), 
('SANDÍA'), ('TARWI'), ('TOMATE'), ('TRIGO'), ('TUNA'), 
('UVA'), ('YACÓN'), ('YUCA'), ('ZANAHORIA'), ('ZAPALLO');

-- GENERAR 1000 CLIENTES (ejemplo con variación)
DO $$
DECLARE
    i INT;
    v_nom TEXT; 
    v_ape TEXT; 
    v_dep_json TEXT;
    v_dep_nombre TEXT;
    v_lat DECIMAL;
    v_lon DECIMAL;
    
    -- Listas extendidas para mayor variedad (30 x 34 = 1020 combinaciones únicas)
    v_nombres TEXT[] := ARRAY['JUAN','MARIA','JOSE','LUIS','CARLOS','ANA','VICTOR','ROSA','MANUEL','ELIZABETH','PEDRO','EDITH','RAUL','HILDA','PERCY','JORGE','GLADYS','WILSON','BETTY','RICARDO','NANCY','OSCAR','SONIA','RUBEN','ALICIA','CESAR','MARTA','HUGO','YOLANDA','FELIX'];
    v_apellidos TEXT[] := ARRAY['QUISPE','MAMANI','FLORES','RODRIGUEZ','HUAMAN','GARCIA','SANCHEZ','PAUCAR','CONDORI','CHAVEZ','MENDOZA','RAMOS','CASTILLO','DIAZ','ESPINOZA','ROJAS','CRUZ','MORALES','GUTIERREZ','REYES','TORRES','VALENCIA','CAVERO','LOPEZ','PURIHUAMAN','AQUINO','YUPANQUI','CUSI','TITO','ZARATE','ANAMPA','CHOQUE','VILCA','HANCCO'];
    
    v_deps TEXT[] := ARRAY[
        '{"d": "AMAZONAS", "lat": -6.2, "lon": -77.8}',
        '{"d": "ANCASH", "lat": -9.5, "lon": -77.5}',
        '{"d": "APURIMAC", "lat": -13.6, "lon": -72.8}',
        '{"d": "AREQUIPA", "lat": -16.4, "lon": -71.5}',
        '{"d": "AYACUCHO", "lat": -13.1, "lon": -74.2}',
        '{"d": "CAJAMARCA", "lat": -7.1, "lon": -78.4}',
        '{"d": "CUSCO", "lat": -13.5, "lon": -71.9}',
        '{"d": "HUANCAVELICA", "lat": -12.7, "lon": -74.9}',
        '{"d": "HUANUCO", "lat": -9.9, "lon": -76.2}',
        '{"d": "ICA", "lat": -14.0, "lon": -75.7}',
        '{"d": "JUNIN", "lat": -11.1, "lon": -75.3}',
        '{"d": "LA LIBERTAD", "lat": -8.1, "lon": -79.0}',
        '{"d": "LAMBAYEQUE", "lat": -6.7, "lon": -79.8}',
        '{"d": "LIMA", "lat": -12.0, "lon": -77.0}',
        '{"d": "LORETO", "lat": -3.7, "lon": -73.2}',
        '{"d": "MADRE DE DIOS", "lat": -12.5, "lon": -69.1}',
        '{"d": "MOQUEGUA", "lat": -17.1, "lon": -70.9}',
        '{"d": "PASCO", "lat": -10.6, "lon": -76.2}',
        '{"d": "PIURA", "lat": -5.1, "lon": -80.6}',
        '{"d": "PUNO", "lat": -15.8, "lon": -70.0}',
        '{"d": "SAN MARTIN", "lat": -6.0, "lon": -76.9}',
        '{"d": "TACNA", "lat": -18.0, "lon": -70.2}',
        '{"d": "TUMBES", "lat": -3.5, "lon": -80.4}',
        '{"d": "UCAYALI", "lat": -8.3, "lon": -74.5}'
    ];
BEGIN
    FOR i IN 1..1000 LOOP
        -- Seleccionar nombre y apellido aleatorios
        v_nom := v_nombres[floor(random() * array_length(v_nombres, 1) + 1)];
        v_ape := v_apellidos[floor(random() * array_length(v_apellidos, 1) + 1)];
        
        -- Seleccionar departamento aleatorio y parsear JSON
        v_dep_json := v_deps[floor(random() * 24 + 1)];
        v_dep_nombre := (v_dep_json::jsonb)->>'d';
        v_lat := ((v_dep_json::jsonb)->>'lat')::decimal;
        v_lon := ((v_dep_json::jsonb)->>'lon')::decimal;
        
        INSERT INTO clientes (
            dni_ruc, 
            entidad_id, 
            nombre, 
            apellido, 
            telefono, 
            correo, 
            latitud, 
            longitud, 
            departamento, 
            provincia, 
            distrito, 
            hectareas, 
            cultivo_id, 
            monto_asegurado, 
            fecha_registro
        ) VALUES (
            -- DNI aleatorio 8 dígitos
            (floor(random() * (99999999 - 10000000 + 1) + 10000000))::text,
            -- Entidad aleatoria (1-12)
            floor(random() * 12 + 1)::int, 
            -- Nombre y apellido
            v_nom, 
            v_ape,
            -- Teléfono 9XXXXXXXX
            '9' || lpad(floor(random() * 100000000)::text, 8, '0'),
            -- Email: nombre.apellido.id@gmail.com (único)
            lower(v_nom || '.' || v_ape || '.' || i || '@gmail.com'),
            -- Coordenadas con variación aleatoria ±0.4 grados
            v_lat + (random() - 0.5) * 0.8, 
            v_lon + (random() - 0.5) * 0.8,
            -- Ubicación
            v_dep_nombre, 
            v_dep_nombre || ' PROVINCIA', 
            v_dep_nombre || ' DISTRITO',
            -- Hectáreas entre 0.5 y 10
            round((random() * 9.5 + 0.5)::numeric, 2), 
            -- Cultivo aleatorio (1-75)
            floor(random() * 75 + 1)::int,
            -- Monto asegurado entre 1,200 y 13,200 soles
            round((random() * 12000 + 1200)::numeric, 2),
            -- Fecha registro entre Sep 2025 y Feb 2026
            '2025-09-01'::timestamp + (random() * 153)::int * interval '1 day'
        ) ON CONFLICT (dni_ruc) DO NOTHING;
    END LOOP;
    
    RAISE NOTICE 'Inserción completada. Verificar con: SELECT COUNT(*) FROM clientes;';
END $$;