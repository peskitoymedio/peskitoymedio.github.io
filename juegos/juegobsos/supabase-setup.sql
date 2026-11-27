-- Ranking del Juego de BSOs de Peskito y Medio.
-- Ejecutar en el SQL Editor del proyecto de Supabase. Es idempotente:
-- se puede volver a ejecutar para actualizar las funciones sin perder datos.

-- pgcrypto aporta hmac() y gen_random_bytes(). En Supabase suele estar ya
-- instalada en el esquema extensions; esto la garantiza.
create extension if not exists pgcrypto with schema extensions;

create table if not exists public.puntuaciones (
  id bigint generated always as identity primary key,
  jugador_id text not null,
  alias text not null check (char_length(btrim(alias)) between 1 and 24),
  puntos integer not null check (puntos between 0 and 1500),
  aciertos integer not null check (aciertos between 0 and 10),
  creado_en timestamptz not null default now()
);

-- Un registro por cada envío, incluso los que no mejoran la marca o se
-- descartan por anti-spam. Es la fuente del contador de partidas.
create table if not exists public.partidas (
  id bigint generated always as identity primary key,
  jugador_id text not null,
  alias text not null,
  puntos integer not null,
  aciertos integer not null,
  creado_en timestamptz not null default now()
);

-- Líder de cada día y de cada semana. Una fila por (periodo, clave) que se
-- actualiza si alguien supera al líder; al cerrar el periodo queda el ganador.
create table if not exists public.victorias (
  periodo text not null check (periodo in ('diario', 'semanal')),
  clave text not null,
  alias text not null,
  puntos integer not null,
  actualizado_en timestamptz not null default now(),
  primary key (periodo, clave)
);

create index if not exists puntuaciones_creado_en_idx on public.puntuaciones (creado_en desc);
create index if not exists puntuaciones_jugador_puntos_idx on public.puntuaciones (jugador_id, puntos desc);
create index if not exists puntuaciones_alias_idx on public.puntuaciones (lower(btrim(alias)));
create index if not exists partidas_creado_en_idx on public.partidas (creado_en desc);
create index if not exists victorias_alias_idx on public.victorias (lower(btrim(alias)));

-- El secreto HMAC vive SOLO aquí. RLS sin políticas: ningún cliente puede
-- leerlo; únicamente las funciones security definer lo usan.
create table if not exists public.ranking_secreto (
  id boolean primary key default true check (id),
  valor text not null
);

-- Una sesión por partida. El token se consume una sola vez al enviar la
-- puntuación; finalizada se marca al terminar, aunque no se envíe.
create table if not exists public.sesiones (
  nonce text primary key,
  creado_en timestamptz not null default now(),
  consumida boolean not null default false,
  consumida_en timestamptz
);
alter table public.sesiones add column if not exists finalizada boolean not null default false;
create index if not exists sesiones_creado_en_idx on public.sesiones (creado_en desc);

-- Contadores globales del juego. Una sola fila; RLS sin políticas.
create table if not exists public.estadisticas (
  id boolean primary key default true check (id),
  partidas_jugadas bigint not null default 0,
  actualizado_en timestamptz not null default now()
);

-- Desglose de la partida ganadora: una fila por pregunta. Solo se consulta
-- desde la RPC detalles_partida; el cliente no puede leerla directamente.
create table if not exists public.detalles_partida (
  puntuacion_id bigint not null references public.puntuaciones (id) on delete cascade,
  orden integer not null check (orden between 1 and 10),
  titulo text not null check (char_length(titulo) between 1 and 100),
  acierto boolean not null,
  elegida text,
  ms integer not null check (ms between 0 and 600000),
  primary key (puntuacion_id, orden)
);

-- RLS activo SIN políticas: nadie puede leer ni escribir estas tablas
-- directamente. Todo pasa por las funciones security definer de abajo.
alter table public.puntuaciones enable row level security;
alter table public.partidas enable row level security;
alter table public.victorias enable row level security;
alter table public.ranking_secreto enable row level security;
alter table public.sesiones enable row level security;
alter table public.estadisticas enable row level security;
alter table public.detalles_partida enable row level security;

-- Recalcula quién lidera el día y la semana actuales.
create or replace function public.actualizar_lideres()
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_periodo text;
  v_clave text;
  v_alias text;
  v_puntos integer;
  v_desde timestamptz;
begin
  for v_periodo, v_clave, v_desde in
    select 'diario',
           to_char(timezone('Europe/Madrid', now()), 'YYYY-MM-DD'),
           date_trunc('day', timezone('Europe/Madrid', now())) at time zone 'Europe/Madrid'
    union all
    select 'semanal',
           to_char(timezone('Europe/Madrid', now()), 'IYYY-"W"IW'),
           date_trunc('week', timezone('Europe/Madrid', now())) at time zone 'Europe/Madrid'
  loop
    select p.alias, p.puntos
      into v_alias, v_puntos
      from public.puntuaciones p
     where p.creado_en >= v_desde
     order by p.puntos desc, p.creado_en asc
     limit 1;

    if v_alias is not null then
      insert into public.victorias (periodo, clave, alias, puntos)
      values (v_periodo, v_clave, v_alias, v_puntos)
      on conflict (periodo, clave) do update
        set alias = excluded.alias,
            puntos = excluded.puntos,
            actualizado_en = now();
    end if;
  end loop;
end;
$$;

-- Token de sesión: se pide al empezar la partida. La firma HMAC se calcula
-- con un secreto que nunca sale de la base de datos, así que un cliente no
-- puede fabricar tokens ni alterar el nonce. Se limpian sesiones antiguas
-- para que la tabla no crezca en el plan gratuito.
create or replace function public.emitir_token()
returns text
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_nonce text;
  v_emitido bigint;
  v_payload text;
  v_secreto text;
begin
  select valor into v_secreto from public.ranking_secreto where id;
  if v_secreto is null then
    v_secreto := encode(gen_random_bytes(32), 'hex');
    insert into public.ranking_secreto (id, valor) values (true, v_secreto)
      on conflict (id) do nothing;
    select valor into v_secreto from public.ranking_secreto where id;
  end if;

  delete from public.sesiones where creado_en < now() - interval '1 day';

  v_nonce := replace(gen_random_uuid()::text, '-', '') ||
             replace(gen_random_uuid()::text, '-', '');
  v_emitido := (extract(epoch from now()) * 1000)::bigint;
  insert into public.sesiones (nonce, creado_en) values (v_nonce, now());

  v_payload := v_nonce || ':' || v_emitido::text;
  return v_payload || '.' || encode(hmac(v_payload, v_secreto, 'sha256'), 'hex');
end;
$$;

-- Se llama al terminar la décima respuesta, aunque el jugador no envíe su
-- puntuación. Valida el token pero NO lo consume: el envío posterior sigue
-- necesitándolo. Marca la sesión como finalizada una sola vez y suma una
-- partida jugada. Si la sesión ya estaba marcada o ha salido de la ventana,
-- no cuenta dos veces.
create or replace function public.registrar_partida_terminada(p_token text)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_payload text;
  v_firma text;
  v_nonce text;
  v_secreto text;
  v_actualizada text;
begin
  if p_token is null or p_token = '' then
    raise exception 'Falta el token de partida';
  end if;
  v_payload := split_part(p_token, '.', 1);
  v_firma := split_part(p_token, '.', 2);
  if v_payload = '' or v_firma = '' then
    raise exception 'Token no válido';
  end if;
  select valor into v_secreto from public.ranking_secreto where id;
  if v_secreto is null then
    raise exception 'Token no válido';
  end if;
  if encode(hmac(v_payload, v_secreto, 'sha256'), 'hex') <> v_firma then
    raise exception 'Token no válido';
  end if;
  v_nonce := split_part(v_payload, ':', 1);

  update public.sesiones
     set finalizada = true
   where nonce = v_nonce
     and not finalizada
     and creado_en <= now() - interval '5 seconds'
     and creado_en >= now() - interval '10 minutes'
  returning nonce into v_actualizada;
  if v_actualizada is null then
    return;
  end if;

  insert into public.estadisticas (id, partidas_jugadas)
  values (true, 1)
  on conflict (id) do update
     set partidas_jugadas = estadisticas.partidas_jugadas + 1,
         actualizado_en = now();
end;
$$;

-- Alta de puntuación. La fecha la pone el servidor; se validan los rangos.
-- El alias (no el navegador) es la identidad: así varias personas pueden
-- jugar desde el mismo ordenador con nombres distintos.
-- Toda llamada válida cuenta como partida. Solo se guarda como marca si
-- supera la mejor del alias en el día actual (hora de España), para que una
-- puntuación peor no sustituya a la mejor de hoy.
-- Devuelve el id de la puntuación que entra en el ranking, o null si la
-- partida no mejora la marca del alias. CREATE OR REPLACE no permite cambiar
-- el tipo de retorno, así que hace falta soltar la firma anterior.
drop function if exists public.registrar_puntuacion(text, text, integer, integer, text, jsonb);

create or replace function public.registrar_puntuacion(
  p_jugador_id text,
  p_alias text,
  p_puntos integer,
  p_aciertos integer,
  p_token text,
  p_detalles jsonb
)
returns bigint
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_payload text;
  v_firma text;
  v_nonce text;
  v_secreto text;
  v_creado timestamptz;
  v_elem jsonb;
  v_titulo text;
  v_acierto boolean;
  v_ms integer;
  v_elegida text;
  v_pts integer;
  v_aciertos_calc integer := 0;
  v_puntos_calc integer := 0;
  v_puntuacion_id bigint;
begin
  if p_jugador_id is null then
    raise exception 'Falta el identificador del jugador';
  end if;
  if char_length(btrim(coalesce(p_alias, ''))) not between 1 and 24 then
    raise exception 'Alias no válido';
  end if;
  if p_puntos is null or p_puntos not between 0 and 1500 then
    raise exception 'Puntuación no válida';
  end if;
  if p_aciertos is null or p_aciertos not between 0 and 10 then
    raise exception 'Número de aciertos no válido';
  end if;
  -- El detalle de la partida es la fuente de la verdad para aciertos y puntos.
  -- Cada acierto vale 100 fijos + round((5000 - ms) / 100) de rapidez, con
  -- ms limitado a 5000. Se usa aritmética exacta (numeric/enteros) para que el
  -- redondeo coincida con el del cliente y no dependa de coma flotante.
  -- Todo esto se valida ANTES de consumir el token o insertar nada.
  if p_detalles is null or jsonb_typeof(p_detalles) <> 'array' then
    raise exception 'Falta el detalle de la partida';
  end if;
  if jsonb_array_length(p_detalles) <> 10 then
    raise exception 'El detalle debe tener 10 respuestas';
  end if;
  for v_elem in select elem from jsonb_array_elements(p_detalles) as t(elem) loop
    v_titulo := nullif(btrim(coalesce(v_elem->>'titulo', '')), '');
    v_acierto := (v_elem->>'acierto')::boolean;
    v_ms := (v_elem->>'ms')::integer;
    v_elegida := nullif(btrim(coalesce(v_elem->>'elegida', '')), '');
    if v_titulo is null or char_length(v_titulo) > 100 then
      raise exception 'Título no válido en el detalle';
    end if;
    if v_acierto is null then
      raise exception 'Acierto no válido en el detalle';
    end if;
    if v_ms is null or v_ms not between 0 and 600000 then
      raise exception 'Tiempo no válido en el detalle';
    end if;
    if v_acierto then
      v_pts := 100 + round((5000 - least(v_ms, 5000))::numeric / 100)::integer;
      v_puntos_calc := v_puntos_calc + v_pts;
      v_aciertos_calc := v_aciertos_calc + 1;
    end if;
  end loop;
  if v_aciertos_calc <> p_aciertos then
    raise exception 'Los aciertos no coinciden con el detalle';
  end if;
  if v_puntos_calc <> p_puntos then
    raise exception 'Los puntos no coinciden con los tiempos del detalle';
  end if;

  -- Verificación del token. La hora se toma de la base de datos, no del
  -- cliente. Mínimo 5 s: con 1 s por pregunta un jugador real tarda ~10 s y
  -- el token se emite antes de cargar el audio. Máximo 10 min.
  if p_token is null or p_token = '' then
    raise exception 'Falta el token de partida';
  end if;
  v_payload := split_part(p_token, '.', 1);
  v_firma := split_part(p_token, '.', 2);
  if v_payload = '' or v_firma = '' then
    raise exception 'Token no válido';
  end if;
  select valor into v_secreto from public.ranking_secreto where id;
  if v_secreto is null then
    raise exception 'Token no válido';
  end if;
  if encode(hmac(v_payload, v_secreto, 'sha256'), 'hex') <> v_firma then
    raise exception 'Token no válido';
  end if;
  v_nonce := split_part(v_payload, ':', 1);

  -- Consumo atómico: un token solo sirve una vez y solo dentro de la ventana.
  update public.sesiones
     set consumida = true, consumida_en = now()
   where nonce = v_nonce
     and not consumida
     and creado_en <= now() - interval '5 seconds'
     and creado_en >= now() - interval '10 minutes'
  returning creado_en into v_creado;
  if v_creado is null then
    raise exception 'Token ya usado o fuera de tiempo';
  end if;

  insert into public.partidas (jugador_id, alias, puntos, aciertos)
  values (p_jugador_id, btrim(p_alias), p_puntos, p_aciertos);

  if exists (
    select 1 from public.puntuaciones
    where lower(btrim(alias)) = lower(btrim(p_alias))
      and timezone('Europe/Madrid', creado_en) >=
          date_trunc('day', timezone('Europe/Madrid', now()))
      and puntos >= p_puntos
  ) then
    return null;
  end if;

  if exists (
    select 1 from public.puntuaciones
    where lower(btrim(alias)) = lower(btrim(p_alias))
      and creado_en > now() - interval '5 seconds'
  ) then
    return null;
  end if;

  insert into public.puntuaciones (jugador_id, alias, puntos, aciertos)
  values (p_jugador_id, btrim(p_alias), p_puntos, p_aciertos)
  returning id into v_puntuacion_id;

  insert into public.detalles_partida (puntuacion_id, orden, titulo, acierto, elegida, ms)
  select v_puntuacion_id,
         t.orden,
         btrim(t.elem->>'titulo'),
         (t.elem->>'acierto')::boolean,
         nullif(btrim(coalesce(t.elem->>'elegida', '')), ''),
         (t.elem->>'ms')::integer
  from jsonb_array_elements(p_detalles) with ordinality as t(elem, orden);

  perform public.actualizar_lideres();
  return v_puntuacion_id;
end;
$$;

-- Cambios de firma: CREATE OR REPLACE no permite alterar argumentos ni tipo
-- de retorno. Las versiones anteriores no exigían token ni detalle.
drop function if exists public.registrar_puntuacion(text, text, integer, integer);
drop function if exists public.registrar_puntuacion(text, text, integer, integer, text);
drop function if exists public.ranking(text);
drop function if exists public.puesto_de(text);
drop function if exists public.puesto_de(text, text);
drop function if exists public.ranking_insignias();
drop function if exists public.puesto_de_insignias(text);
drop function if exists public.total_partidas();

-- Ranking por periodo. Se queda con la MEJOR partida de cada alias, no con
-- la suma, para no premiar a quien más juega. Día y semana en Europe/Madrid.
-- Los trofeos son acumulados: cuentan todas las victorias del alias, esté en
-- la pestaña que esté.
create or replace function public.ranking(p_periodo text default 'diario')
returns table (
  puesto bigint,
  alias text,
  puntos integer,
  aciertos integer,
  fecha date,
  victorias_diarias bigint,
  victorias_semanales bigint,
  es_campeon_historico boolean,
  partida_id bigint
)
language sql
stable
security definer
set search_path = public
as $$
  with campeon as (
    select lower(btrim(p.alias)) as clave
    from public.puntuaciones p
    order by p.puntos desc, p.creado_en asc
    limit 1
  ),
  filtradas as (
    select p.*
    from public.puntuaciones p
    where (
            p_periodo = 'semanal'
            and timezone('Europe/Madrid', p.creado_en) >=
                date_trunc('week', timezone('Europe/Madrid', now()))
          )
       or (
            p_periodo = 'diario'
            and timezone('Europe/Madrid', p.creado_en) >=
                date_trunc('day', timezone('Europe/Madrid', now()))
          )
       or p_periodo = 'historico'
  ),
  mejores as (
    select distinct on (lower(btrim(f.alias)))
           f.id, f.alias, f.puntos, f.aciertos, f.creado_en
    from filtradas f
    order by lower(btrim(f.alias)), f.puntos desc, f.creado_en asc
  )
  select row_number() over (order by m.puntos desc, m.creado_en asc) as puesto,
         m.alias,
         m.puntos,
         m.aciertos,
         timezone('Europe/Madrid', m.creado_en)::date as fecha,
         (select count(*) from public.victorias v
           where v.periodo = 'diario'
             and lower(btrim(v.alias)) = lower(btrim(m.alias))) as victorias_diarias,
         (select count(*) from public.victorias v
           where v.periodo = 'semanal'
             and lower(btrim(v.alias)) = lower(btrim(m.alias))) as victorias_semanales,
          exists (select 1 from campeon c where c.clave = lower(btrim(m.alias))) as es_campeon_historico,
  m.id as partida_id
  from mejores m
  order by m.puntos desc, m.creado_en asc
  limit 50;
$$;

-- Puesto de un alias en el periodo indicado, aunque quede fuera del top 50.
-- Devuelve las mismas columnas que ranking() para reutilizar el detalle.
create or replace function public.puesto_de(
  p_alias text,
  p_periodo text default 'diario'
)
returns table (
  puesto bigint,
  alias text,
  puntos integer,
  aciertos integer,
  fecha date,
  victorias_diarias bigint,
  victorias_semanales bigint,
  es_campeon_historico boolean,
  partida_id bigint
)
language sql
stable
security definer
set search_path = public
as $$
  with campeon as (
    select lower(btrim(p.alias)) as clave
    from public.puntuaciones p
    order by p.puntos desc, p.creado_en asc
    limit 1
  ),
  filtradas as (
    select p.*
    from public.puntuaciones p
    where (
            p_periodo = 'semanal'
            and timezone('Europe/Madrid', p.creado_en) >=
                date_trunc('week', timezone('Europe/Madrid', now()))
          )
       or (
            p_periodo = 'diario'
            and timezone('Europe/Madrid', p.creado_en) >=
                date_trunc('day', timezone('Europe/Madrid', now()))
          )
       or p_periodo = 'historico'
  ),
  mejores as (
    select distinct on (lower(btrim(f.alias)))
           f.id, f.alias, f.puntos, f.aciertos, f.creado_en
    from filtradas f
    order by lower(btrim(f.alias)), f.puntos desc, f.creado_en asc
  ),
  clasificacion as (
    select row_number() over (order by m.puntos desc, m.creado_en asc) as puesto,
           m.id, m.alias, m.puntos, m.aciertos, m.creado_en
    from mejores m
  )
  select c.puesto,
         c.alias,
         c.puntos,
         c.aciertos,
         timezone('Europe/Madrid', c.creado_en)::date as fecha,
         (select count(*) from public.victorias v
           where v.periodo = 'diario'
             and lower(btrim(v.alias)) = lower(btrim(c.alias))) as victorias_diarias,
         (select count(*) from public.victorias v
           where v.periodo = 'semanal'
             and lower(btrim(v.alias)) = lower(btrim(c.alias))) as victorias_semanales,
                 exists (select 1 from campeon cam where cam.clave = lower(btrim(c.alias))) as es_campeon_historico,
  c.id as partida_id
  from clasificacion c
  where lower(btrim(c.alias)) = lower(btrim(p_alias))
  order by c.puesto
  limit 1;
$$;

-- Ranking de insignias: solo alias con al menos una victoria diaria o semanal.
-- Se ordena por semanales, luego diarias y, si empatan, por mejor marca histórica.
-- La "mejor marca" es la mejor puntuación histórica del alias, no la de la última victoria.
-- La corona (es_campeon_historico) marca al primero del ranking histórico.
create or replace function public.ranking_insignias()
returns table (
  puesto bigint,
  alias text,
  victorias_semanales bigint,
  victorias_diarias bigint,
  puntos integer,
  aciertos integer,
  es_campeon_historico boolean,
  partida_id bigint
)
language sql
stable
security definer
set search_path = public
as $$
  with trofeos as (
    select lower(btrim(v.alias)) as clave,
           count(*) filter (where v.periodo = 'semanal') as semanales,
           count(*) filter (where v.periodo = 'diario') as diarias
    from public.victorias v
    group by lower(btrim(v.alias))
  ),
  mejores as (
    select distinct on (lower(btrim(p.alias)))
           lower(btrim(p.alias)) as clave, p.alias, p.puntos, p.aciertos, p.id, p.creado_en
    from public.puntuaciones p
    order by lower(btrim(p.alias)), p.puntos desc, p.creado_en asc
  ),
  campeon as (
    select m.clave
    from mejores m
    order by m.puntos desc, m.creado_en asc
    limit 1
  )
  select row_number() over (
           order by t.semanales desc, t.diarias desc, m.puntos desc
         ) as puesto,
         m.alias,
         t.semanales,
         t.diarias,
         m.puntos,
         m.aciertos,
         (c.clave is not null) as es_campeon_historico,
         m.id as partida_id
  from (
    select clave, semanales, diarias from trofeos
    union all
    select c.clave, 0::bigint, 0::bigint from campeon c
    where not exists (select 1 from trofeos t2 where t2.clave = c.clave)
  ) t
  join mejores m on m.clave = t.clave
  left join campeon c on c.clave = t.clave
  order by t.semanales desc, t.diarias desc, m.puntos desc
  limit 50;
$$;

-- Puesto de un alias en el ranking de insignias, aunque quede fuera del top 50.
create or replace function public.puesto_de_insignias(p_alias text)
returns table (
  puesto bigint,
  alias text,
  victorias_semanales bigint,
  victorias_diarias bigint,
  puntos integer,
  aciertos integer,
  es_campeon_historico boolean,
  partida_id bigint
)
language sql
stable
security definer
set search_path = public
as $$
  with trofeos as (
    select lower(btrim(v.alias)) as clave,
           count(*) filter (where v.periodo = 'semanal') as semanales,
           count(*) filter (where v.periodo = 'diario') as diarias
    from public.victorias v
    group by lower(btrim(v.alias))
  ),
  mejores as (
    select distinct on (lower(btrim(p.alias)))
           lower(btrim(p.alias)) as clave, p.alias, p.puntos, p.aciertos, p.id, p.creado_en
    from public.puntuaciones p
    order by lower(btrim(p.alias)), p.puntos desc, p.creado_en asc
  ),
  campeon as (
    select m.clave
    from mejores m
    order by m.puntos desc, m.creado_en asc
    limit 1
  ),
  clasificados as (
    select row_number() over (
             order by t.semanales desc, t.diarias desc, m.puntos desc
           ) as puesto,
           t.clave,
           m.alias,
           t.semanales as victorias_semanales,
           t.diarias as victorias_diarias,
           m.puntos,
           m.aciertos,
           (c.clave is not null) as es_campeon_historico,
           m.id as partida_id
    from (
      select clave, semanales, diarias from trofeos
      union all
      select c.clave, 0::bigint, 0::bigint from campeon c
      where not exists (select 1 from trofeos t2 where t2.clave = c.clave)
    ) t
    join mejores m on m.clave = t.clave
    left join campeon c on c.clave = t.clave
  )
  select puesto, alias, victorias_semanales, victorias_diarias,
         puntos, aciertos, es_campeon_historico, partida_id
  from clasificados
  where clave = lower(btrim(p_alias))
  order by puesto
  limit 1;
$$;

create or replace function public.total_partidas()
returns bigint
language sql
stable
security definer
set search_path = public
as $$
  select count(*) from public.partidas;
$$;

create or replace function public.total_partidas_jugadas()
returns bigint
language sql
stable
security definer
set search_path = public
as $$
  select coalesce((select partidas_jugadas from public.estadisticas where id), 0);
$$;

-- Desglose de una partida del ranking: solo se puede pedir por el id que
-- devuelve ranking(). RLS impide leer la tabla directamente.
create or replace function public.detalles_partida(p_id bigint)
returns table (
  orden integer,
  titulo text,
  acierto boolean,
  elegida text,
  segundos numeric
)
language sql
stable
security definer
set search_path = public
as $$
  select d.orden,
         d.titulo,
         d.acierto,
         d.elegida,
         round(d.ms::numeric / 1000, 2) as segundos
  from public.detalles_partida d
  where d.puntuacion_id = p_id
  order by d.orden;
$$;

-- Datos ya existentes: el contador arranca con las partidas que había, y se
-- calculan los líderes del día y la semana actuales.
insert into public.partidas (jugador_id, alias, puntos, aciertos, creado_en)
select p.jugador_id, p.alias, p.puntos, p.aciertos, p.creado_en
from public.puntuaciones p
where not exists (select 1 from public.partidas);

-- El contador de partidas jugadas arranca en 219, el número de sesiones
-- abiertas al empezar a medirlo. on conflict conserva el valor acumulado
-- cuando el script se vuelve a ejecutar.
insert into public.estadisticas (id, partidas_jugadas)
values (true, 219)
on conflict (id) do nothing;

select public.actualizar_lideres();

revoke all on function public.actualizar_lideres() from public;
revoke all on function public.emitir_token() from public;

revoke all on function public.registrar_puntuacion(text, text, integer, integer, text, jsonb) from public;
revoke all on function public.ranking(text) from public;
revoke all on function public.puesto_de(text, text) from public;
revoke all on function public.ranking_insignias() from public;
revoke all on function public.puesto_de_insignias(text) from public;
revoke all on function public.total_partidas() from public;
revoke all on function public.total_partidas_jugadas() from public;
revoke all on function public.registrar_partida_terminada(text) from public;
revoke all on function public.detalles_partida(bigint) from public;

grant execute on function public.emitir_token() to anon, authenticated;
grant execute on function public.registrar_puntuacion(text, text, integer, integer, text, jsonb) to anon, authenticated;
grant execute on function public.ranking(text) to anon, authenticated;
grant execute on function public.puesto_de(text, text) to anon, authenticated;
grant execute on function public.ranking_insignias() to anon, authenticated;
grant execute on function public.puesto_de_insignias(text) to anon, authenticated;
grant execute on function public.total_partidas() to anon, authenticated;
grant execute on function public.total_partidas_jugadas() to anon, authenticated;
grant execute on function public.registrar_partida_terminada(text) to anon, authenticated;
grant execute on function public.detalles_partida(bigint) to anon, authenticated;
