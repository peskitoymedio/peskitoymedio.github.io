/*
 * Configuración del ranking online del Juego de BSOs.
 *
 * 1. Crea un proyecto en https://supabase.com/dashboard/new
 * 2. Pega el contenido de supabase-setup.sql en el SQL Editor y ejecútalo.
 * 3. Copia aquí los valores de Project Settings > API:
 *      Project URL (solo la base, SIN /rest/v1) -> supabaseUrl
 *      Publishable key (o anon public)          -> supabaseAnonKey
 *
 * Mientras estos valores estén vacíos, el juego funciona igual que antes y
 * la página de ranking muestra un aviso en lugar de dar error.
 */
window.PYM_CONFIG = {
  supabaseUrl: "https://tttjmlqpnqoztvhmevwa.supabase.co",
  supabaseAnonKey: "sb_publishable_AmJKA_oQfDRHxwDI-MDj-Q_em815SXz"
};
