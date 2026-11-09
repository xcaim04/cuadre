-- Un nombre se compara sin mayúsculas, tildes ni espacios de más.
CREATE OR REPLACE MACRO normalizar(x) AS strip_accents(lower(trim(regexp_replace(x, '\s+', ' ', 'g'))));
