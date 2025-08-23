# ===============================
# PÁGINA ADMIN COMPLETA
# ===============================
def page_admin():
    require_login()
    user = st.session_state["user"]
    if user["role"] != "admin":
        st.warning("Área restrita a administradores.")
        st.stop()

    st.header("⚙️ Painel Admin • Gerenciamento de Usuários")
    st.markdown("Aqui você pode gerenciar usuários, atualizar PIX, planos e visualizar indicadores.")

    # Tabela de usuários
    df = db_query("""
        SELECT id, username, full_name, email, plan, stage, received_stage_donations, pix_key, referrer_id, created_at
        FROM users ORDER BY id
    """, as_df=True)

    st.subheader("Usuários Cadastrados")
    for idx, row in df.iterrows():
        st.markdown(f"**{row['full_name']} ({row['username']})**")
        st.write(f"- Email: {row['email'] or '—'}")
        st.write(
            f"- Stage: {row['stage']} | Doações recebidas: {row['received_stage_donations']} | Plano: {row['plan']}")
        st.write(
            f"- PIX: {row['pix_key'] or '—'} | Indicação (referrer): {row['referrer_id'] or '—'} | Criado em: {row['created_at']}")

        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.button(f"Excluir {row['username']}", key=f"del_{row['id']}"):
                db_execute("DELETE FROM users WHERE id = ?", (row['id'],))
                log_action(user['id'], "DELETE_USER", {"deleted_user": row['username']})
                st.success(f"Usuário {row['username']} excluído com sucesso!")
                st.experimental_rerun()
        with col2:
            new_pix = st.text_input(f"PIX {row['username']}", value=row['pix_key'] or "", key=f"pix_{row['id']}")
            if st.button(f"Atualizar PIX {row['username']}", key=f"btn_pix_{row['id']}"):
                db_execute("UPDATE users SET pix_key = ? WHERE id = ?", (new_pix, row['id']))
                log_action(user['id'], "UPDATE_PIX", {"user": row['username'], "new_pix": new_pix})
                st.success(f"PIX de {row['username']} atualizado!")
                st.experimental_rerun()
        with col3:
