const API_URL = '/api';

const ui = {
    apiKey: document.getElementById('api_key'),
    resetKeyBtn: document.getElementById('reset_key_btn'),
    loadBtn: document.getElementById('load_btn'),
    itemSelect: document.getElementById('item_select'),
    minPrice: document.getElementById('min_price'),
    addTaskBtn: document.getElementById('add_task_btn'),
    taskList: document.getElementById('task_list'),
    countBadge: document.getElementById('count'),
    startBtn: document.getElementById('start_btn'),
    stopBtn: document.getElementById('stop_btn'),
    logOutput: document.getElementById('log_output')
};

let logInterval;

// проверка апи ключа
const savedKey = localStorage.getItem('csgo_api_key');
if (savedKey) {
    ui.apiKey.value = savedKey;
    ui.apiKey.disabled = true;
    ui.resetKeyBtn.style.display = 'block';
}

// забыть API-ключ
ui.resetKeyBtn.addEventListener('click', () => {
    localStorage.removeItem('csgo_api_key');
    ui.apiKey.value = '';
    ui.apiKey.disabled = false;
    ui.resetKeyBtn.style.display = 'none';

    ui.itemSelect.innerHTML = '<option value="">Сначала загрузите инвентарь...</option>';
    ui.itemSelect.disabled = true;
    ui.minPrice.disabled = true;
    ui.minPrice.value = '';
    ui.addTaskBtn.disabled = true;
});

// загрузка инвентаря
ui.loadBtn.addEventListener('click', async () => {
    if (!ui.apiKey.value) return alert("Введите API ключ");

    localStorage.setItem('csgo_api_key', ui.apiKey.value);
    ui.loadBtn.innerText = "Загрузка...";
    ui.loadBtn.disabled = true;

    try {
        const res = await fetch(`${API_URL}/get_inventory`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: ui.apiKey.value })
        });
        const data = await res.json();

        ui.itemSelect.innerHTML = '';

        if (data.items && data.items.length > 0) {
            data.items.forEach(item => {
                const opt = document.createElement('option');
                opt.value = item.item_id;
                opt.dataset.hash = item.market_hash_name;
                opt.text = `${item.market_hash_name} (${item.price.toFixed(2)} руб)`;
                ui.itemSelect.appendChild(opt);
            });

            ui.apiKey.disabled = true;
            ui.resetKeyBtn.style.display = 'block';
            ui.itemSelect.disabled = false;
            ui.minPrice.disabled = false;
            ui.addTaskBtn.disabled = false;
        } else {
            ui.itemSelect.innerHTML = '<option>Нет предметов на продаже</option>';
        }
    } catch (err) {
        alert("Ошибка связи с сервером бэкенда.");
        console.error(err);
    } finally {
        ui.loadBtn.innerText = "1. Загрузить инвентарь на продаже";
        ui.loadBtn.disabled = false;
    }
});

ui.addTaskBtn.addEventListener('click', async () => {
    if (!ui.minPrice.value) return alert("Укажите минимальную цену!");

    const opt = ui.itemSelect.options[ui.itemSelect.selectedIndex];

    await fetch(`${API_URL}/add_task`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            api_key: ui.apiKey.value,
            item_id: opt.value,
            hash_name: opt.dataset.hash,
            min_price: parseFloat(ui.minPrice.value)
        })
    });

    ui.minPrice.value = '';
    updateTasks();
});

window.removeTask = async function (itemId) {
    await fetch(`${API_URL}/remove_task`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_id: itemId })
    });
    updateTasks();
};

async function updateTasks() {
    try {
        const res = await fetch(`${API_URL}/tasks`);
        const data = await res.json();
        const tasks = data.tasks;
        const count = Object.keys(tasks).length;

        ui.countBadge.textContent = `${count} агентов`;
        ui.taskList.innerHTML = '';

        if (count === 0) {
            ui.taskList.innerHTML = '<div class="empty">Очередь пуста</div>';
            return;
        }

        for (const [itemId, task] of Object.entries(tasks)) {
            const div = document.createElement('div');
            div.className = 'task-item';
            div.innerHTML = `
                <div>
                    <div class="row">
                        <span class="tag sell">DUMP</span>
                        <span class="name">${task.hash_name}</span>
                    </div>
                    <div class="sub-row">
                        <span>Порог:</span>
                        <span class="price">${task.min_price.toFixed(2)} ₽</span>
                        <span class="live">Active</span>
                    </div>
                </div>
                <button class="btn danger stop" onclick="removeTask('${itemId}')">Stop</button>
            `;
            ui.taskList.appendChild(div);
        }
    } catch (err) {
        console.error("Ошибка загрузки очереди из БД", err);
    }
}

ui.startBtn.addEventListener('click', async () => {
    const res = await fetch(`${API_URL}/start`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
        ui.startBtn.disabled = true;
        ui.stopBtn.disabled = false;
        startLogs();
    }
});

ui.stopBtn.addEventListener('click', async () => {
    await fetch(`${API_URL}/stop`, { method: 'POST' });
    ui.startBtn.disabled = false;
    ui.stopBtn.disabled = true;
    if (logInterval) clearInterval(logInterval);
});

function startLogs() {
    if (logInterval) clearInterval(logInterval);

    logInterval = setInterval(async () => {
        try {
            const res = await fetch(`${API_URL}/logs`);
            const data = await res.json();
            if (data.logs && data.logs.length > 0) {
                ui.logOutput.innerHTML = data.logs.map(l => {
                    return `<div><span class="caret">›</span>${l}</div>`;
                }).join('');
                ui.logOutput.scrollTop = ui.logOutput.scrollHeight;
            }
        } catch (err) {
            console.error("Ошибка обновления логов терминала", err);
        }
    }, 2000);
}

updateTasks();