const usersTableBody = document.getElementById("usersTableBody");
const usersStatus = document.getElementById("usersStatus");
const reloadUsersBtn = document.getElementById("reloadUsersBtn");

function setUsersStatus(text, error = false) {
  usersStatus.textContent = text;
  usersStatus.style.color = error ? "#8a2f13" : "";
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch]);
}

function formatStatus(user) {
  return user.is_active ? "启用" : "停用";
}

async function loadUsers() {
  setUsersStatus("正在读取用户列表...");
  const data = await window.T0Auth.fetchJson("/api/users");
  const users = data.users || [];
  if (!users.length) {
    usersTableBody.innerHTML = `<tr><td colspan="7">暂无用户。</td></tr>`;
    setUsersStatus("没有用户记录。", true);
    return;
  }
  usersTableBody.innerHTML = users.map((user) => `
    <tr data-username="${escapeHtml(user.username)}">
      <td>${escapeHtml(user.username)}</td>
      <td>${escapeHtml(user.display_name || "")}</td>
      <td>${user.role === "admin" ? "管理员" : "普通用户"}</td>
      <td>${formatStatus(user)}</td>
      <td>${escapeHtml(user.created_at || "")}</td>
      <td>${escapeHtml(user.last_login_at || "")}</td>
      <td>
        <div class="user-admin-actions">
          <button type="button" class="secondary" data-action="toggle" ${user.username === "admin" ? "disabled" : ""}>${user.is_active ? "禁用" : "启用"}</button>
          <button type="button" class="secondary" data-action="reset" ${user.username === "admin" ? "disabled" : ""}>重置密码</button>
        </div>
      </td>
    </tr>
  `).join("");
  setUsersStatus(`已读取 ${users.length} 个用户。`);
}

usersTableBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const row = button.closest("tr[data-username]");
  const username = row?.dataset.username || "";
  if (!username) return;
  try {
    if (button.dataset.action === "toggle") {
      const shouldEnable = button.textContent.trim() === "启用";
      await window.T0Auth.fetchJson(`/api/users/${encodeURIComponent(username)}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: shouldEnable }),
      });
      setUsersStatus(`${username} 状态已更新。`);
    } else if (button.dataset.action === "reset") {
      const newPassword = window.prompt(`请输入 ${username} 的新密码（至少8位）`);
      if (!newPassword) return;
      await window.T0Auth.fetchJson(`/api/users/${encodeURIComponent(username)}/password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_password: newPassword }),
      });
      setUsersStatus(`${username} 密码已重置。`);
    }
    await loadUsers();
  } catch (error) {
    setUsersStatus(error.message, true);
  }
});

reloadUsersBtn.addEventListener("click", () => loadUsers().catch((error) => setUsersStatus(error.message, true)));

window.T0Auth.loadCurrentUser()
  .then(loadUsers)
  .catch((error) => setUsersStatus(error.message, true));
