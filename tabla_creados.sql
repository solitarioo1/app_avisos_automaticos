-- 1) ENTIDADES
CREATE TABLE entidades (
  id SERIAL PRIMARY KEY,
  nombre VARCHAR(100) UNIQUE NOT NULL
);

-- 2) CULTIVOS
CREATE TABLE tabla_cultivos (
  id SERIAL PRIMARY KEY,
  nombre VARCHAR(50) UNIQUE NOT NULL
);

-- 3) CLIENTES
CREATE TABLE clientes (
  id SERIAL PRIMARY KEY, 
  dni_ruc VARCHAR(20) UNIQUE,
  entidad_id INT REFERENCES entidades(id),
  nombre VARCHAR(100) NOT NULL,
  apellido VARCHAR(100) NOT NULL,
  telefono VARCHAR(15),
  correo VARCHAR(100) UNIQUE,
  latitud DECIMAL(9,6) NOT NULL,
  longitud DECIMAL(9,6) NOT NULL,
  departamento VARCHAR(50) NOT NULL,
  provincia VARCHAR(50),
  distrito VARCHAR(50),
  hectareas DECIMAL(8,2),
  cultivo_id INT REFERENCES tabla_cultivos(id),
  monto_asegurado DECIMAL(12,2),
  estado VARCHAR(20) DEFAULT 'activo',
  fecha_registro TIMESTAMP DEFAULT NOW(),
  ultima_actualizacion TIMESTAMP DEFAULT NOW()
);

-- INDICES
CREATE INDEX idx_cliente_ubicacion ON clientes(departamento, provincia, distrito);
CREATE INDEX idx_cliente_coords ON clientes(latitud, longitud);
CREATE INDEX idx_cliente_estado ON clientes(estado);