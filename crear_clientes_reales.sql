-- ============================================================================
-- SCRIPT: GENERAR 500 CLIENTES CON UBICACIONES REALES DEL PERÚ
-- Departamentos, Provincias y Distritos REALES con coordenadas correctas
-- ============================================================================

-- Primero eliminar datos existentes (opcional)
-- TRUNCATE TABLE clientes RESTART IDENTITY CASCADE;

-- GENERAR 500 CLIENTES CON UBICACIONES REALES
DO $$
DECLARE
    i INT;
    v_nom TEXT; 
    v_ape TEXT; 
    v_ubicacion JSONB;
    v_dep TEXT;
    v_prov TEXT;
    v_dist TEXT;
    v_lat DECIMAL;
    v_lon DECIMAL;
    v_idx INT;
    
    -- Nombres y apellidos peruanos
    v_nombres TEXT[] := ARRAY['JUAN','MARIA','JOSE','LUIS','CARLOS','ANA','VICTOR','ROSA','MANUEL','ELIZABETH','PEDRO','EDITH','RAUL','HILDA','PERCY','JORGE','GLADYS','WILSON','BETTY','RICARDO','NANCY','OSCAR','SONIA','RUBEN','ALICIA','CESAR','MARTA','HUGO','YOLANDA','FELIX'];
    v_apellidos TEXT[] := ARRAY['QUISPE','MAMANI','FLORES','RODRIGUEZ','HUAMAN','GARCIA','SANCHEZ','PAUCAR','CONDORI','CHAVEZ','MENDOZA','RAMOS','CASTILLO','DIAZ','ESPINOZA','ROJAS','CRUZ','MORALES','GUTIERREZ','REYES','TORRES','VALENCIA','CAVERO','LOPEZ','PURIHUAMAN','AQUINO','YUPANQUI','CUSI','TITO','ZARATE','ANAMPA','CHOQUE','VILCA','HANCCO'];
    
    -- UBICACIONES REALES: departamento, provincia, distrito, latitud, longitud
    v_ubicaciones JSONB[] := ARRAY[
        -- PUNO (zona agrícola importante)
        '{"dep":"PUNO","prov":"EL COLLAO","dist":"ILAVE","lat":-16.0833,"lon":-69.6333}'::jsonb,
        '{"dep":"PUNO","prov":"EL COLLAO","dist":"CAPAZO","lat":-17.1833,"lon":-69.7333}'::jsonb,
        '{"dep":"PUNO","prov":"EL COLLAO","dist":"PILCUYO","lat":-16.1167,"lon":-69.5333}'::jsonb,
        '{"dep":"PUNO","prov":"EL COLLAO","dist":"SANTA ROSA","lat":-16.7833,"lon":-69.8667}'::jsonb,
        '{"dep":"PUNO","prov":"CHUCUITO","dist":"JULI","lat":-16.2167,"lon":-69.4667}'::jsonb,
        '{"dep":"PUNO","prov":"CHUCUITO","dist":"DESAGUADERO","lat":-16.5667,"lon":-69.0333}'::jsonb,
        '{"dep":"PUNO","prov":"CHUCUITO","dist":"POMATA","lat":-16.2667,"lon":-69.2833}'::jsonb,
        '{"dep":"PUNO","prov":"CHUCUITO","dist":"ZEPITA","lat":-16.5000,"lon":-69.1000}'::jsonb,
        '{"dep":"PUNO","prov":"PUNO","dist":"PUNO","lat":-15.8402,"lon":-70.0219}'::jsonb,
        '{"dep":"PUNO","prov":"PUNO","dist":"ACORA","lat":-15.9667,"lon":-69.8000}'::jsonb,
        '{"dep":"PUNO","prov":"PUNO","dist":"ATUNCOLLA","lat":-15.6833,"lon":-70.1500}'::jsonb,
        '{"dep":"PUNO","prov":"PUNO","dist":"CAPACHICA","lat":-15.6167,"lon":-69.8333}'::jsonb,
        '{"dep":"PUNO","prov":"AZANGARO","dist":"AZANGARO","lat":-14.9100,"lon":-70.1900}'::jsonb,
        '{"dep":"PUNO","prov":"AZANGARO","dist":"ASILLO","lat":-14.7833,"lon":-70.3500}'::jsonb,
        '{"dep":"PUNO","prov":"MELGAR","dist":"AYAVIRI","lat":-14.8833,"lon":-70.5833}'::jsonb,
        '{"dep":"PUNO","prov":"LAMPA","dist":"LAMPA","lat":-15.3667,"lon":-70.3667}'::jsonb,
        '{"dep":"PUNO","prov":"SAN ROMAN","dist":"JULIACA","lat":-15.5000,"lon":-70.1333}'::jsonb,
        '{"dep":"PUNO","prov":"HUANCANE","dist":"HUANCANE","lat":-15.2000,"lon":-69.7667}'::jsonb,
        
        -- AREQUIPA
        '{"dep":"AREQUIPA","prov":"AREQUIPA","dist":"AREQUIPA","lat":-16.3989,"lon":-71.5350}'::jsonb,
        '{"dep":"AREQUIPA","prov":"AREQUIPA","dist":"CAYMA","lat":-16.3667,"lon":-71.5500}'::jsonb,
        '{"dep":"AREQUIPA","prov":"AREQUIPA","dist":"CERRO COLORADO","lat":-16.3833,"lon":-71.5833}'::jsonb,
        '{"dep":"AREQUIPA","prov":"AREQUIPA","dist":"CHARACATO","lat":-16.4667,"lon":-71.4833}'::jsonb,
        '{"dep":"AREQUIPA","prov":"AREQUIPA","dist":"CHIGUATA","lat":-16.4000,"lon":-71.4000}'::jsonb,
        '{"dep":"AREQUIPA","prov":"AREQUIPA","dist":"MOLLEBAYA","lat":-16.4833,"lon":-71.4500}'::jsonb,
        '{"dep":"AREQUIPA","prov":"AREQUIPA","dist":"PAUCARPATA","lat":-16.4333,"lon":-71.5000}'::jsonb,
        '{"dep":"AREQUIPA","prov":"AREQUIPA","dist":"SABANDIA","lat":-16.4500,"lon":-71.4667}'::jsonb,
        '{"dep":"AREQUIPA","prov":"AREQUIPA","dist":"SACHACA","lat":-16.4167,"lon":-71.5667}'::jsonb,
        '{"dep":"AREQUIPA","prov":"AREQUIPA","dist":"SOCABAYA","lat":-16.4667,"lon":-71.5333}'::jsonb,
        '{"dep":"AREQUIPA","prov":"CAYLLOMA","dist":"CHIVAY","lat":-15.6383,"lon":-71.6008}'::jsonb,
        '{"dep":"AREQUIPA","prov":"CAYLLOMA","dist":"ACHOMA","lat":-15.6500,"lon":-71.7833}'::jsonb,
        '{"dep":"AREQUIPA","prov":"CAYLLOMA","dist":"CABANACONDE","lat":-15.6167,"lon":-71.9667}'::jsonb,
        '{"dep":"AREQUIPA","prov":"CAYLLOMA","dist":"COPORAQUE","lat":-15.6333,"lon":-71.6833}'::jsonb,
        '{"dep":"AREQUIPA","prov":"CAYLLOMA","dist":"ICHUPAMPA","lat":-15.6000,"lon":-71.7333}'::jsonb,
        '{"dep":"AREQUIPA","prov":"CAYLLOMA","dist":"LARI","lat":-15.6000,"lon":-71.8167}'::jsonb,
        '{"dep":"AREQUIPA","prov":"CAYLLOMA","dist":"MACA","lat":-15.6333,"lon":-71.7667}'::jsonb,
        '{"dep":"AREQUIPA","prov":"CAYLLOMA","dist":"MADRIGAL","lat":-15.6167,"lon":-71.8500}'::jsonb,
        '{"dep":"AREQUIPA","prov":"CAYLLOMA","dist":"YANQUE","lat":-15.6500,"lon":-71.6667}'::jsonb,
        '{"dep":"AREQUIPA","prov":"ISLAY","dist":"MOLLENDO","lat":-17.0233,"lon":-72.0147}'::jsonb,
        '{"dep":"AREQUIPA","prov":"ISLAY","dist":"COCACHACRA","lat":-17.0000,"lon":-71.7667}'::jsonb,
        '{"dep":"AREQUIPA","prov":"ISLAY","dist":"DEAN VALDIVIA","lat":-17.0333,"lon":-71.7333}'::jsonb,
        '{"dep":"AREQUIPA","prov":"ISLAY","dist":"ISLAY","lat":-17.0167,"lon":-72.1000}'::jsonb,
        '{"dep":"AREQUIPA","prov":"ISLAY","dist":"MEJIA","lat":-17.1333,"lon":-71.8500}'::jsonb,
        '{"dep":"AREQUIPA","prov":"ISLAY","dist":"PUNTA DE BOMBON","lat":-17.1500,"lon":-71.8000}'::jsonb,
        
        -- CUSCO
        '{"dep":"CUSCO","prov":"CUSCO","dist":"CUSCO","lat":-13.5183,"lon":-71.9781}'::jsonb,
        '{"dep":"CUSCO","prov":"CUSCO","dist":"CCORCA","lat":-13.5500,"lon":-72.1333}'::jsonb,
        '{"dep":"CUSCO","prov":"CUSCO","dist":"POROY","lat":-13.4833,"lon":-72.0500}'::jsonb,
        '{"dep":"CUSCO","prov":"CUSCO","dist":"SAN JERONIMO","lat":-13.5500,"lon":-71.9000}'::jsonb,
        '{"dep":"CUSCO","prov":"CUSCO","dist":"SAN SEBASTIAN","lat":-13.5333,"lon":-71.9333}'::jsonb,
        '{"dep":"CUSCO","prov":"CUSCO","dist":"SANTIAGO","lat":-13.5333,"lon":-72.0000}'::jsonb,
        '{"dep":"CUSCO","prov":"CUSCO","dist":"SAYLLA","lat":-13.5667,"lon":-71.8333}'::jsonb,
        '{"dep":"CUSCO","prov":"CUSCO","dist":"WANCHAQ","lat":-13.5333,"lon":-71.9500}'::jsonb,
        '{"dep":"CUSCO","prov":"CALCA","dist":"CALCA","lat":-13.3167,"lon":-71.9500}'::jsonb,
        '{"dep":"CUSCO","prov":"CALCA","dist":"PISAC","lat":-13.4167,"lon":-71.8500}'::jsonb,
        '{"dep":"CUSCO","prov":"URUBAMBA","dist":"URUBAMBA","lat":-13.3050,"lon":-72.1167}'::jsonb,
        '{"dep":"CUSCO","prov":"URUBAMBA","dist":"CHINCHERO","lat":-13.3833,"lon":-72.0500}'::jsonb,
        '{"dep":"CUSCO","prov":"URUBAMBA","dist":"HUAYLLABAMBA","lat":-13.2500,"lon":-72.1167}'::jsonb,
        '{"dep":"CUSCO","prov":"URUBAMBA","dist":"MACHUPICCHU","lat":-13.1631,"lon":-72.5450}'::jsonb,
        '{"dep":"CUSCO","prov":"URUBAMBA","dist":"MARAS","lat":-13.3333,"lon":-72.1500}'::jsonb,
        '{"dep":"CUSCO","prov":"URUBAMBA","dist":"OLLANTAYTAMBO","lat":-13.2578,"lon":-72.2639}'::jsonb,
        '{"dep":"CUSCO","prov":"URUBAMBA","dist":"YUCAY","lat":-13.3167,"lon":-72.0833}'::jsonb,
        '{"dep":"CUSCO","prov":"LA CONVENCION","dist":"SANTA ANA","lat":-12.8667,"lon":-72.6833}'::jsonb,
        '{"dep":"CUSCO","prov":"LA CONVENCION","dist":"ECHARATE","lat":-12.7833,"lon":-72.5667}'::jsonb,
        '{"dep":"CUSCO","prov":"LA CONVENCION","dist":"MARANURA","lat":-12.9500,"lon":-72.6667}'::jsonb,
        
        -- APURIMAC
        '{"dep":"APURIMAC","prov":"ABANCAY","dist":"ABANCAY","lat":-13.6339,"lon":-72.8814}'::jsonb,
        '{"dep":"APURIMAC","prov":"ABANCAY","dist":"CHACOCHE","lat":-13.7167,"lon":-72.8500}'::jsonb,
        '{"dep":"APURIMAC","prov":"ABANCAY","dist":"CIRCA","lat":-13.7500,"lon":-72.9500}'::jsonb,
        '{"dep":"APURIMAC","prov":"ABANCAY","dist":"CURAHUASI","lat":-13.5500,"lon":-72.7333}'::jsonb,
        '{"dep":"APURIMAC","prov":"ABANCAY","dist":"HUANIPACA","lat":-13.5333,"lon":-72.9167}'::jsonb,
        '{"dep":"APURIMAC","prov":"ABANCAY","dist":"LAMBRAMA","lat":-13.9000,"lon":-72.7167}'::jsonb,
        '{"dep":"APURIMAC","prov":"ABANCAY","dist":"PICHIRHUA","lat":-13.7000,"lon":-72.9833}'::jsonb,
        '{"dep":"APURIMAC","prov":"ABANCAY","dist":"SAN PEDRO DE CACHORA","lat":-13.5167,"lon":-72.8167}'::jsonb,
        '{"dep":"APURIMAC","prov":"ABANCAY","dist":"TAMBURCO","lat":-13.5667,"lon":-72.8833}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"ANDAHUAYLAS","lat":-13.6556,"lon":-73.3878}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"ANDARAPA","lat":-13.5500,"lon":-73.3667}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"CHIARA","lat":-13.5833,"lon":-73.4333}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"HUANCARAMA","lat":-13.5000,"lon":-73.1500}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"HUANCARAY","lat":-13.5167,"lon":-73.5333}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"KISHUARA","lat":-13.5667,"lon":-73.2333}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"PACOBAMBA","lat":-13.4333,"lon":-73.0833}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"PACUCHA","lat":-13.6000,"lon":-73.3333}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"PAMPACHIRI","lat":-14.2000,"lon":-73.5833}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"SAN ANTONIO DE CACHI","lat":-13.5167,"lon":-73.6167}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"SAN JERONIMO","lat":-13.6500,"lon":-73.3500}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"SAN MIGUEL DE CHACCRAMPA","lat":-13.4833,"lon":-73.5833}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"SANTA MARIA DE CHICMO","lat":-13.5333,"lon":-73.5500}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"TALAVERA","lat":-13.6500,"lon":-73.4167}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"TUMAY HUARACA","lat":-14.0333,"lon":-73.6333}'::jsonb,
        '{"dep":"APURIMAC","prov":"ANDAHUAYLAS","dist":"TURPO","lat":-13.7500,"lon":-73.4833}'::jsonb,
        
        -- AYACUCHO
        '{"dep":"AYACUCHO","prov":"HUAMANGA","dist":"AYACUCHO","lat":-13.1588,"lon":-74.2239}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUAMANGA","dist":"ACOCRO","lat":-13.2167,"lon":-74.0500}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUAMANGA","dist":"ACOS VINCHOS","lat":-13.1833,"lon":-74.0667}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUAMANGA","dist":"CARMEN ALTO","lat":-13.1833,"lon":-74.2167}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUAMANGA","dist":"CHIARA","lat":-13.2667,"lon":-74.2000}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUAMANGA","dist":"OCROS","lat":-13.4000,"lon":-73.9500}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUAMANGA","dist":"PACAYCASA","lat":-13.0500,"lon":-74.2167}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUAMANGA","dist":"QUINUA","lat":-13.0333,"lon":-74.1333}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUAMANGA","dist":"SAN JOSE DE TICLLAS","lat":-13.1333,"lon":-74.3167}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUAMANGA","dist":"SAN JUAN BAUTISTA","lat":-13.1667,"lon":-74.2167}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUAMANGA","dist":"SANTIAGO DE PISCHA","lat":-13.0833,"lon":-74.3833}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUAMANGA","dist":"SOCOS","lat":-13.2000,"lon":-74.2833}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUAMANGA","dist":"TAMBILLO","lat":-13.2333,"lon":-74.1167}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUAMANGA","dist":"VINCHOS","lat":-13.2500,"lon":-74.3333}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUANTA","dist":"HUANTA","lat":-12.9375,"lon":-74.2458}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUANTA","dist":"AYAHUANCO","lat":-12.6333,"lon":-74.2167}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUANTA","dist":"HUAMANGUILLA","lat":-12.9667,"lon":-74.2000}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUANTA","dist":"IGUAIN","lat":-12.9833,"lon":-74.2167}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUANTA","dist":"LURICOCHA","lat":-12.8833,"lon":-74.2667}'::jsonb,
        '{"dep":"AYACUCHO","prov":"HUANTA","dist":"SANTILLANA","lat":-12.7833,"lon":-74.1333}'::jsonb,
        
        -- JUNIN
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"HUANCAYO","lat":-12.0667,"lon":-75.2097}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"CARHUACALLANGA","lat":-12.2000,"lon":-75.3167}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"CHACAPAMPA","lat":-12.1833,"lon":-75.3333}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"CHICCHE","lat":-12.1500,"lon":-75.2833}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"CHILCA","lat":-12.0833,"lon":-75.2000}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"CHONGOS ALTO","lat":-12.2167,"lon":-75.2667}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"CHUPURO","lat":-12.2500,"lon":-75.1167}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"COLCA","lat":-12.1667,"lon":-75.1333}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"CULLHUAS","lat":-12.2667,"lon":-75.1500}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"EL TAMBO","lat":-12.0500,"lon":-75.2167}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"HUACRAPUQUIO","lat":-12.2833,"lon":-75.1167}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"HUALHUAS","lat":-12.0000,"lon":-75.2500}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"HUANCAN","lat":-12.1167,"lon":-75.1500}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"HUASICANCHA","lat":-12.2333,"lon":-75.3000}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"HUAYUCACHI","lat":-12.1333,"lon":-75.2000}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"INGENIO","lat":-11.8833,"lon":-75.2833}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"PARIAHUANCA","lat":-11.9833,"lon":-74.9667}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"PILCOMAYO","lat":-12.0500,"lon":-75.2500}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"PUCARA","lat":-12.2000,"lon":-75.1667}'::jsonb,
        '{"dep":"JUNIN","prov":"HUANCAYO","dist":"QUICHUAY","lat":-11.9167,"lon":-75.2667}'::jsonb,
        
        -- HUANCAVELICA
        '{"dep":"HUANCAVELICA","prov":"HUANCAVELICA","dist":"HUANCAVELICA","lat":-12.7833,"lon":-74.9667}'::jsonb,
        '{"dep":"HUANCAVELICA","prov":"HUANCAVELICA","dist":"ACOBAMBILLA","lat":-12.6000,"lon":-75.0500}'::jsonb,
        '{"dep":"HUANCAVELICA","prov":"HUANCAVELICA","dist":"ACORIA","lat":-12.6333,"lon":-74.8667}'::jsonb,
        '{"dep":"HUANCAVELICA","prov":"HUANCAVELICA","dist":"CONAYCA","lat":-12.6167,"lon":-74.9000}'::jsonb,
        '{"dep":"HUANCAVELICA","prov":"HUANCAVELICA","dist":"CUENCA","lat":-12.6000,"lon":-75.0000}'::jsonb,
        '{"dep":"HUANCAVELICA","prov":"HUANCAVELICA","dist":"HUACHOCOLPA","lat":-13.0333,"lon":-74.9500}'::jsonb,
        '{"dep":"HUANCAVELICA","prov":"HUANCAVELICA","dist":"HUAYLLAHUARA","lat":-12.7167,"lon":-75.2000}'::jsonb,
        '{"dep":"HUANCAVELICA","prov":"HUANCAVELICA","dist":"IZCUCHACA","lat":-12.5000,"lon":-74.9833}'::jsonb,
        '{"dep":"HUANCAVELICA","prov":"HUANCAVELICA","dist":"LARIA","lat":-12.5333,"lon":-75.0167}'::jsonb,
        '{"dep":"HUANCAVELICA","prov":"HUANCAVELICA","dist":"MANTA","lat":-12.6500,"lon":-75.1000}'::jsonb,
        
        -- TACNA
        '{"dep":"TACNA","prov":"TACNA","dist":"TACNA","lat":-18.0056,"lon":-70.2489}'::jsonb,
        '{"dep":"TACNA","prov":"TACNA","dist":"ALTO DE LA ALIANZA","lat":-17.9833,"lon":-70.2500}'::jsonb,
        '{"dep":"TACNA","prov":"TACNA","dist":"CALANA","lat":-17.9333,"lon":-70.1833}'::jsonb,
        '{"dep":"TACNA","prov":"TACNA","dist":"CIUDAD NUEVA","lat":-17.9667,"lon":-70.2500}'::jsonb,
        '{"dep":"TACNA","prov":"TACNA","dist":"INCLAN","lat":-17.8833,"lon":-70.3000}'::jsonb,
        '{"dep":"TACNA","prov":"TACNA","dist":"PACHIA","lat":-17.8833,"lon":-70.1500}'::jsonb,
        '{"dep":"TACNA","prov":"TACNA","dist":"PALCA","lat":-17.7500,"lon":-69.9667}'::jsonb,
        '{"dep":"TACNA","prov":"TACNA","dist":"POCOLLAY","lat":-17.9833,"lon":-70.2167}'::jsonb,
        '{"dep":"TACNA","prov":"TACNA","dist":"SAMA","lat":-17.7833,"lon":-70.4833}'::jsonb,
        '{"dep":"TACNA","prov":"TACNA","dist":"CORONEL GREGORIO ALBARRACIN LANCHIPA","lat":-18.0333,"lon":-70.2667}'::jsonb,
        '{"dep":"TACNA","prov":"CANDARAVE","dist":"CANDARAVE","lat":-17.2700,"lon":-70.2500}'::jsonb,
        '{"dep":"TACNA","prov":"CANDARAVE","dist":"CAIRANI","lat":-17.3000,"lon":-70.3333}'::jsonb,
        '{"dep":"TACNA","prov":"CANDARAVE","dist":"CAMILACA","lat":-17.2833,"lon":-70.4167}'::jsonb,
        '{"dep":"TACNA","prov":"CANDARAVE","dist":"CURIBAYA","lat":-17.2167,"lon":-70.3500}'::jsonb,
        '{"dep":"TACNA","prov":"CANDARAVE","dist":"HUANUARA","lat":-17.3167,"lon":-70.2833}'::jsonb,
        '{"dep":"TACNA","prov":"CANDARAVE","dist":"QUILAHUANI","lat":-17.3333,"lon":-70.2333}'::jsonb,
        '{"dep":"TACNA","prov":"JORGE BASADRE","dist":"LOCUMBA","lat":-17.6167,"lon":-70.7667}'::jsonb,
        '{"dep":"TACNA","prov":"JORGE BASADRE","dist":"ILABAYA","lat":-17.4167,"lon":-70.5167}'::jsonb,
        '{"dep":"TACNA","prov":"JORGE BASADRE","dist":"ITE","lat":-17.8500,"lon":-70.9500}'::jsonb,
        '{"dep":"TACNA","prov":"TARATA","dist":"TARATA","lat":-17.4744,"lon":-70.0336}'::jsonb,
        
        -- MOQUEGUA
        '{"dep":"MOQUEGUA","prov":"MARISCAL NIETO","dist":"MOQUEGUA","lat":-17.1939,"lon":-70.9356}'::jsonb,
        '{"dep":"MOQUEGUA","prov":"MARISCAL NIETO","dist":"CARUMAS","lat":-16.8167,"lon":-70.7000}'::jsonb,
        '{"dep":"MOQUEGUA","prov":"MARISCAL NIETO","dist":"CUCHUMBAYA","lat":-16.7500,"lon":-70.6667}'::jsonb,
        '{"dep":"MOQUEGUA","prov":"MARISCAL NIETO","dist":"SAMEGUA","lat":-17.1833,"lon":-70.9000}'::jsonb,
        '{"dep":"MOQUEGUA","prov":"MARISCAL NIETO","dist":"SAN CRISTOBAL","lat":-16.7333,"lon":-70.7333}'::jsonb,
        '{"dep":"MOQUEGUA","prov":"MARISCAL NIETO","dist":"TORATA","lat":-17.0833,"lon":-70.8500}'::jsonb,
        '{"dep":"MOQUEGUA","prov":"GENERAL SANCHEZ CERRO","dist":"OMATE","lat":-16.6667,"lon":-70.9833}'::jsonb,
        '{"dep":"MOQUEGUA","prov":"GENERAL SANCHEZ CERRO","dist":"CHOJATA","lat":-16.5833,"lon":-70.7167}'::jsonb,
        '{"dep":"MOQUEGUA","prov":"GENERAL SANCHEZ CERRO","dist":"COALAQUE","lat":-16.6167,"lon":-70.7333}'::jsonb,
        '{"dep":"MOQUEGUA","prov":"GENERAL SANCHEZ CERRO","dist":"ICHUÑA","lat":-16.1500,"lon":-70.5500}'::jsonb,
        '{"dep":"MOQUEGUA","prov":"ILO","dist":"ILO","lat":-17.6411,"lon":-71.3428}'::jsonb,
        '{"dep":"MOQUEGUA","prov":"ILO","dist":"EL ALGARROBAL","lat":-17.5833,"lon":-71.3833}'::jsonb,
        '{"dep":"MOQUEGUA","prov":"ILO","dist":"PACOCHA","lat":-17.5333,"lon":-71.2167}'::jsonb
    ];

BEGIN
    FOR i IN 1..500 LOOP
        -- Seleccionar nombre y apellido aleatorios
        v_nom := v_nombres[floor(random() * array_length(v_nombres, 1) + 1)];
        v_ape := v_apellidos[floor(random() * array_length(v_apellidos, 1) + 1)];
        
        -- Seleccionar ubicación aleatoria de las reales
        v_idx := floor(random() * array_length(v_ubicaciones, 1) + 1);
        v_ubicacion := v_ubicaciones[v_idx];
        
        v_dep := v_ubicacion->>'dep';
        v_prov := v_ubicacion->>'prov';
        v_dist := v_ubicacion->>'dist';
        v_lat := (v_ubicacion->>'lat')::decimal;
        v_lon := (v_ubicacion->>'lon')::decimal;
        
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
            -- Email único
            lower(v_nom || '.' || v_ape || '.' || i || '@gmail.com'),
            -- Coordenadas con pequeña variación (±0.02 grados = ~2km)
            v_lat + (random() - 0.5) * 0.04, 
            v_lon + (random() - 0.5) * 0.04,
            -- Ubicación REAL
            v_dep, 
            v_prov, 
            v_dist,
            -- Hectáreas entre 0.5 y 15
            round((random() * 14.5 + 0.5)::numeric, 2), 
            -- Cultivo aleatorio (1-75)
            floor(random() * 75 + 1)::int,
            -- Monto asegurado entre 2,000 y 25,000 soles
            round((random() * 23000 + 2000)::numeric, 2),
            -- Fecha registro entre Sep 2025 y Feb 2026
            '2025-09-01'::timestamp + (random() * 153)::int * interval '1 day'
        ) ON CONFLICT (dni_ruc) DO NOTHING;
    END LOOP;
    
    RAISE NOTICE '✅ 500 clientes con ubicaciones REALES insertados correctamente';
END $$;

-- VERIFICAR
SELECT 
    departamento,
    provincia,
    distrito,
    COUNT(*) as clientes,
    ROUND(SUM(hectareas)::numeric, 2) as total_hectareas,
    ROUND(SUM(monto_asegurado)::numeric, 2) as total_monto
FROM clientes
GROUP BY departamento, provincia, distrito
ORDER BY departamento, provincia, distrito;
