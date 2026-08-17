-- ============================================================
-- DOSSEL — Schema de produtores, propriedades, cálculos e contratos
-- Migration: 20260718120000_schema_produtores
--
-- Contexto:
--   O projeto já tem uma tabela `leads` (captação no site) e um
--   backend FastAPI (car_integration.py) que consulta o SICAR e
--   devolve dados de propriedade + cálculo de carbono. Este schema
--   formaliza o que acontece DEPOIS do lead: quando um produtor tem
--   conta (Supabase Auth), suas propriedades, os cálculos de carbono
--   feitos para elas e os contratos de participação.
--
--   Os nomes de coluna em `propriedades` e `calculos_carbono`
--   espelham 1:1 os campos já devolvidos por /consultar-car/{car},
--   para que o backend possa gravar a resposta da API direto no banco
--   sem camada de tradução.
--
-- Como aplicar:
--   - Supabase Dashboard → SQL Editor → cole e rode este arquivo, ou
--   - `supabase db push` se o CLI estiver linkado ao projeto.
--
-- Não mexe na tabela `leads` existente — ela já está em produção e
-- não foi inspecionada nesta sessão; qualquer integração com ela deve
-- ser feita manualmente depois de confirmar as colunas reais.
-- ============================================================

-- ── produtores ──────────────────────────────────────────────
-- Perfil do produtor rural, 1:1 com auth.users (login do portal).
create table if not exists public.produtores (
  id            uuid primary key references auth.users(id) on delete cascade,
  nome_completo text,
  cpf_cnpj      text unique,
  email         text,
  telefone      text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

comment on table public.produtores is 'Perfil do produtor rural, criado automaticamente no signup (auth.users).';

-- ── propriedades ────────────────────────────────────────────
-- Fazendas/propriedades do produtor, alimentadas pela consulta ao CAR/SICAR.
create table if not exists public.propriedades (
  id                uuid primary key default gen_random_uuid(),
  produtor_id       uuid references public.produtores(id) on delete set null,
  numero_car        text unique not null,
  nome              text,
  municipio         text,
  estado            char(2),
  bioma             text check (bioma in ('Amazônia', 'Cerrado', 'Mata Atlântica', 'Caatinga', 'Pantanal', 'Pampa')),
  situacao_car      text,
  condicao          text,
  area_total_ha     numeric(12, 2),
  area_app_ha       numeric(12, 2),
  area_reserva_ha   numeric(12, 2),
  area_vegetacao_ha numeric(12, 2),
  area_elegivel_ha  numeric(12, 2),
  pct_vegetacao     numeric(5, 2),
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

comment on table public.propriedades is 'Propriedades rurais vinculadas a um produtor, uma linha por CAR consultado.';

create index if not exists propriedades_produtor_id_idx on public.propriedades (produtor_id);

-- ── calculos_carbono ────────────────────────────────────────
-- Histórico de cálculos de potencial de carbono por propriedade.
-- Append-only: cada consulta ao backend gera uma nova linha (preço do
-- tCO2 e área elegível mudam ao longo do tempo).
create table if not exists public.calculos_carbono (
  id                     uuid primary key default gen_random_uuid(),
  propriedade_id         uuid not null references public.propriedades(id) on delete cascade,
  bioma_usado            text not null,
  area_elegivel_ha       numeric(12, 2) not null,
  pct_vegetacao          numeric(5, 2),
  co2_anual_tco2         numeric(12, 2) not null,
  preco_tco2_brl         numeric(10, 2) not null,
  receita_bruta_ano      numeric(12, 2) not null,
  receita_produtor_ano   numeric(12, 2) not null,
  receita_dossel_ano     numeric(12, 2) not null,
  receita_produtor_10anos numeric(12, 2),
  potencial              text check (potencial in ('Alto', 'Médio', 'Baixo')),
  calculado_em           timestamptz not null default now()
);

comment on table public.calculos_carbono is 'Snapshot de cada cálculo de potencial de carbono rodado para uma propriedade.';

create index if not exists calculos_carbono_propriedade_id_idx on public.calculos_carbono (propriedade_id);

-- ── contratos ────────────────────────────────────────────────
-- Contratos de participação entre a Dossel e o produtor.
create table if not exists public.contratos (
  id                  uuid primary key default gen_random_uuid(),
  propriedade_id      uuid not null references public.propriedades(id) on delete cascade,
  produtor_id         uuid not null references public.produtores(id) on delete cascade,
  status              text not null default 'rascunho'
                        check (status in ('rascunho', 'enviado', 'assinado', 'ativo', 'cancelado')),
  percentual_produtor numeric(5, 2) not null default 85,
  percentual_dossel   numeric(5, 2) not null default 15,
  documento_url       text,
  assinado_em         timestamptz,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  constraint contratos_percentuais_check check (percentual_produtor + percentual_dossel = 100)
);

comment on table public.contratos is 'Contrato de participação (85/15) entre produtor e Dossel para uma propriedade.';

create index if not exists contratos_propriedade_id_idx on public.contratos (propriedade_id);
create index if not exists contratos_produtor_id_idx on public.contratos (produtor_id);

-- ── updated_at automático ───────────────────────────────────
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger set_updated_at before update on public.produtores
  for each row execute function public.set_updated_at();

create trigger set_updated_at before update on public.propriedades
  for each row execute function public.set_updated_at();

create trigger set_updated_at before update on public.contratos
  for each row execute function public.set_updated_at();

-- ── auto-provisionamento do perfil no signup ────────────────
-- Quando um produtor cria conta via Supabase Auth, cria a linha
-- correspondente em public.produtores automaticamente.
create or replace function public.handle_new_produtor()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.produtores (id, email, nome_completo, telefone)
  values (
    new.id,
    new.email,
    new.raw_user_meta_data ->> 'nome_completo',
    new.raw_user_meta_data ->> 'telefone'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_produtor();

-- ── Row Level Security ───────────────────────────────────────
-- Regra geral: produtor só enxerga/edita os próprios dados.
-- Cálculos e contratos são gravados pelo backend (service role, que
-- ignora RLS) ou pelo futuro painel interno — por isso não têm
-- policy de INSERT/UPDATE para o papel authenticated.

alter table public.produtores enable row level security;
alter table public.propriedades enable row level security;
alter table public.calculos_carbono enable row level security;
alter table public.contratos enable row level security;

create policy "Produtor vê o próprio perfil"
  on public.produtores for select
  using (auth.uid() = id);

create policy "Produtor atualiza o próprio perfil"
  on public.produtores for update
  using (auth.uid() = id)
  with check (auth.uid() = id);

create policy "Produtor vê as próprias propriedades"
  on public.propriedades for select
  using (auth.uid() = produtor_id);

create policy "Produtor cadastra propriedade própria"
  on public.propriedades for insert
  with check (auth.uid() = produtor_id);

create policy "Produtor atualiza propriedade própria"
  on public.propriedades for update
  using (auth.uid() = produtor_id)
  with check (auth.uid() = produtor_id);

create policy "Produtor vê cálculos das próprias propriedades"
  on public.calculos_carbono for select
  using (
    exists (
      select 1 from public.propriedades p
      where p.id = calculos_carbono.propriedade_id
        and p.produtor_id = auth.uid()
    )
  );

create policy "Produtor vê os próprios contratos"
  on public.contratos for select
  using (auth.uid() = produtor_id);
