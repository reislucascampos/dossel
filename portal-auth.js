// ============================================================
// DOSSEL — Autenticação compartilhada dos painéis (produtor / equipe)
// Depende do supabase-js (carregado via CDN antes deste script) e
// das tabelas `produtores` / `equipe` (ver supabase/migrations/).
// ============================================================

const SUPABASE_URL = "https://ejxyfijhynpxyncqtpvy.supabase.co";
const SUPABASE_KEY = "sb_publishable_1vDT3Dhesla7IRrcXOtOoA_SpYdf_k_";

const dosselSupabase = supabase.createClient(SUPABASE_URL, SUPABASE_KEY);

function initials(nome) {
  if (!nome) return "?";
  const parts = nome.trim().split(/\s+/);
  const first = parts[0]?.[0] || "";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

async function dosselLogout() {
  await dosselSupabase.auth.signOut();
  window.location.href = "login.html";
}

// Garante que existe sessão e que o usuário pertence ao papel
// esperado ("produtor" ou "equipe"). Redireciona para login.html
// (sem sessão) ou para a área correta (papel errado).
// Devolve { user, perfil } para a página preencher nome/avatar.
async function requireSession(papelEsperado) {
  const {
    data: { session },
  } = await dosselSupabase.auth.getSession();

  if (!session) {
    window.location.href = "login.html";
    return null;
  }

  const user = session.user;

  if (papelEsperado === "equipe") {
    const { data: perfil } = await dosselSupabase
      .from("equipe")
      .select("nome_completo, cargo, ativo")
      .eq("id", user.id)
      .maybeSingle();

    if (!perfil || !perfil.ativo) {
      window.location.href = "portal-produtor.html";
      return null;
    }
    return { user, perfil };
  }

  // papelEsperado === "produtor"
  const { data: souEquipe } = await dosselSupabase
    .from("equipe")
    .select("id")
    .eq("id", user.id)
    .maybeSingle();

  if (souEquipe) {
    window.location.href = "painel-interno.html";
    return null;
  }

  const { data: perfil } = await dosselSupabase
    .from("produtores")
    .select("nome_completo, email")
    .eq("id", user.id)
    .maybeSingle();

  return { user, perfil };
}
