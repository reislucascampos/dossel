-- ============================================================
-- DOSSEL — Schema da equipe interna (painel admin)
-- Migration: 20260817120000_schema_equipe
--
-- Contexto:
--   [[dossel_project_overview]] já tem login seguro de produtor via
--   Supabase Auth (schema_produtores). Esta migration adiciona o
--   mesmo padrão para a EQUIPE DA DOSSEL: membros internos que
--   acessam um painel admin para ver/gerenciar produtores,
--   propriedades, cálculos de carbono e contratos.
--
--   Login continua 100% via Supabase Auth (auth.users) — nenhuma
--   senha é armazenada em tabela nossa. `equipe` só guarda o perfil
--   (nome, cargo) vinculado 1:1 ao usuário autenticado.
--
-- Como aplicar:
--   - Supabase Dashboard → SQL Editor → cole e rode este arquivo.
--     ATENÇÃO: NÃO use "Run without RLS" — isso remove as instruções
--     de RLS/policy do script antes de rodar, deixando as tabelas
--     sem proteção. Rode normal.
--   - ou `supabase db push` se o CLI estiver linkado ao projeto.
--
--   Depois de rodar: para promover alguém a admin, crie o usuário
--   no Supabase Auth (convite por e-mail) e então rode:
--     insert into public.equipe (id, nome_completo, cargo)
--     values ('<uuid-do-usuario>', 'Nome', 'admin');
--   Não existe policy de INSERT para `equipe` — só o dashboard do
--   Supabase (service role) pode adicionar membros, de propósito.
-- ============================================================

-- ── equipe ──────────────────────────────────────────────────
-- Perfil de membro interno da Dossel, 1:1 com auth.users.
create table if not exists public.equipe (
  id            uuid primary key references auth.users(id) on delete cascade,
  nome_completo text not null,
  email         text,
  cargo         text not null default 'operacional'
                  check (cargo in ('admin', 'operacional')),
  ativo         boolean not null default true,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

comment on table public.equipe is 'Perfil de membro da equipe interna da Dossel (painel admin). Cadastro manual via service role, não há signup público.';

create trigger set_updated_at before update on public.equipe
  for each row execute function public.set_updated_at();

-- ── helper: is_equipe() ─────────────────────────────────────
-- security definer pra poder checar a tabela `equipe` mesmo de
-- dentro de policies de OUTRAS tabelas (produtores, contratos...)
-- sem precisar dar select público em `equipe`.
create or replace function public.is_equipe()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1 from public.equipe
    where id = auth.uid() and ativo
  );
$$;

comment on function public.is_equipe() is 'True se o usuário autenticado é membro ativo da equipe interna (qualquer cargo).';

-- ── Row Level Security: equipe ───────────────────────────────
alter table public.equipe enable row level security;

create policy "Membro da equipe vê o próprio perfil"
  on public.equipe for select
  using (auth.uid() = id);

create policy "Equipe vê os perfis uns dos outros"
  on public.equipe for select
  using (public.is_equipe());

-- ── Acesso da equipe aos dados de produtor ───────────────────
-- Painel admin: equipe enxerga e mantém tudo. Produtor continua
-- só vendo o que é seu (policies do schema_produtores intactas).

create policy "Equipe vê todos os produtores"
  on public.produtores for select
  using (public.is_equipe());

create policy "Equipe vê todas as propriedades"
  on public.propriedades for select
  using (public.is_equipe());

create policy "Equipe gerencia propriedades"
  on public.propriedades for update
  using (public.is_equipe())
  with check (public.is_equipe());

create policy "Equipe vê todos os cálculos de carbono"
  on public.calculos_carbono for select
  using (public.is_equipe());

create policy "Equipe insere cálculos de carbono"
  on public.calculos_carbono for insert
  with check (public.is_equipe());

create policy "Equipe vê todos os contratos"
  on public.contratos for select
  using (public.is_equipe());

create policy "Equipe gerencia contratos"
  on public.contratos for all
  using (public.is_equipe())
  with check (public.is_equipe());
