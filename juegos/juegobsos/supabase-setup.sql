-- Ranking del Juego de BSOs de Peskito y Medio.
-- Ejecutar una sola vez en el SQL Editor del proyecto de Supabase.

create table if not exists public.puntuaciones (
  id bigint generated always as identity primary key,
  jugador_id text not null,
  alias text not null check (char_length(btrim(alias)) between 1 and 24),
  puntos integer not null check (puntos between 0 and 1500),
  aciertos integer not null check (aciertos between 0 and 10),
  creado_en timestamptz not null default now()
);

create index if not exists puntuaciones_creado_en_idx on public.puntuaciones (creado_en desc);
create index if not exists puntuaciones_jugador_puntos_idx on public.puntuaciones (jugador_id, puntos desc);

-- RLS activo SIN políticas: nadie puede leer ni escribir la tabla directamente.
-- Todo pasa por las dos funciones security definer de abajo.
alter table public.puntuaciones enable row level security;

-- Alta de puntuación. La fecha la pone el servidor; se validan los rangos y
-- se ignora un segundo envío del mismo jugador en menos de 5 segundos.
create or replace function public.registrar_puntuacion(
  p_jugador_id text,
  p_alias text,
  p_puntos integer,
  p_aciertos integer
)
returns void
language plpgsql
security definer
set search_path = public
as $$
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

  if exists (
    select 1 from public.puntuaciones
    where jugador_id = p_jugador_id
      and creado_en > now() - interval '5 seconds'
  ) then
    return;
  end if;

  insert into public.puntuaciones (jugador_id, alias, puntos, aciertos)
  values (p_jugador_id, btrim(p_alias), p_puntos, p_aciertos);
end;
$$;

-- Ranking por periodo. Se queda con la MEJOR partida de cada jugador,
-- no con la suma, para no premiar a quien más juega.
-- Semana y mes se calculan en hora de España (Europe/Madrid).
create or replace function public.ranking(p_periodo text default 'semanal')
returns table (
  puesto bigint,
  alias text,
  puntos integer,
  aciertos integer,
  fecha date
)
language sql
stable
security definer
set search_path = public
as $$
  with filtradas as (
    select p.*
    from public.puntuaciones p
    where (
            p_periodo = 'semanal'
            and timezone('Europe/Madrid', p.creado_en) >=
                date_trunc('week', timezone('Europe/Madrid', now()))
          )
       or (
            p_periodo = 'mensual'
            and timezone('Europe/Madrid', p.creado_en) >=
                date_trunc('month', timezone('Europe/Madrid', now()))
          )
       or p_periodo = 'historico'
  ),
  mejores as (
    select distinct on (f.jugador_id)
           f.jugador_id, f.alias, f.puntos, f.aciertos, f.creado_en
    from filtradas f
    order by f.jugador_id, f.puntos desc, f.creado_en asc
  )
  select row_number() over (order by m.puntos desc, m.creado_en asc) as puesto,
         m.alias,
         m.puntos,
         m.aciertos,
         timezone('Europe/Madrid', m.creado_en)::date as fecha
  from mejores m
  order by m.puntos desc, m.creado_en asc
  limit 50;
$$;

revoke all on function public.registrar_puntuacion(text, text, integer, integer) from public;
revoke all on function public.ranking(text) from public;
grant execute on function public.registrar_puntuacion(text, text, integer, integer) to anon, authenticated;
grant execute on function public.ranking(text) to anon, authenticated;
