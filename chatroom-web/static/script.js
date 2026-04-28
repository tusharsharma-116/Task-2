const socket = io();

let senderName = 'User' + Math.floor(Math.random() * 1000);

// Status
socket.on('status', (data) => {
    document.getElementById('status').textContent = data.msg;
});

// Receive message
socket.on('receive_message', (data) => {
    addMessage(data.sender, data.message);
});

// History
socket.on('chat_history', (history) => {
    history.forEach(msg => {
        addMessage(msg.sender, msg.message, msg.timestamp);
    });
});

function addMessage(sender, message, timestamp = new Date()) {
    const messagesDiv = document.getElementById('messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender === senderName ? 'user' : 'ai'}`;
    
    const timeStr = timestamp ? new Date(timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '';
    
    messageDiv.innerHTML = `
        <div class="sender">${sender}</div>
        <div>${message}</div>
        <div class="time">${timeStr}</div>
    `;
    
    messagesDiv.appendChild(messageDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    if (message && message !== '') {
        socket.emit('send_message', {
            sender: senderName,
            message: message
        });
        input.value = '';
    }
}

function loadHistory() {
    socket.emit('get_history');
}

// Events
document.getElementById('messageInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

document.querySelector('.input-group button').addEventListener('click', sendMessage);

// Image upload
function uploadImage() {
    const fileInput = document.getElementById('imageInput');
    const file = fileInput.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
        socket.emit('upload_image', {image: e.target.result});
        fileInput.value = '';
    };
    reader.readAsDataURL(file);
}

// Audio upload
function uploadAudio() {
    const fileInput = document.getElementById('audioInput');
    const file = fileInput.files[0];
    if (!file || file.size > 5*1024*1024) {
        alert('Audio ≤5MB');
        return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
        document.getElementById('status').textContent = 'Uploading audio...';
        console.log('uploadAudio: emitting upload_audio');
        socket.emit('upload_audio', {audio: e.target.result});
        fileInput.value = '';
    };
    reader.readAsDataURL(file);
}



socket.on('image_results', (data) => {
    document.getElementById('origImg').src = data.original;
    document.getElementById('compImg').src = data.compressed;
    document.getElementById('edgeImg').src = data.edges;
    document.getElementById('kpImg').src = data.keypoints;
    document.getElementById('metrics').textContent = data.metrics;
    document.getElementById('aiDesc').textContent = data.ai_desc;
    document.getElementById('imageResults').style.display = 'block';
});

// Audio results
socket.on('audio_results', (data) => {
    console.log('audio_results received', data);
    const origImg = document.getElementById('audioOrigSpec');
    const compImg = document.getElementById('audioCompSpec');
    if (data.orig_spec) {
        origImg.src = data.orig_spec;
        origImg.style.display = '';
    } else {
        origImg.src = '';
        origImg.style.display = 'none';
    }
    if (data.comp_spec) {
        compImg.src = data.comp_spec;
        compImg.style.display = '';
    } else {
        compImg.src = '';
        compImg.style.display = 'none';
    }
    document.getElementById('audioAiDesc').textContent = data.ai_desc || '';
    const table = document.getElementById('audioTable').tBodies[0];
    table.innerHTML = '';
    if (Array.isArray(data.table) && data.table.length > 0) {
        data.table.forEach(row => {
            const tr = table.insertRow();
            tr.innerHTML = `<td>${row.bitrate}</td><td>${row.size}</td><td>${row.mse}</td><td>${row.snr}</td>`;
        });
    } else {
        const tr = table.insertRow();
        tr.innerHTML = `<td colspan="4">No compression rows generated</td>`;
    }
    document.getElementById('audioResults').style.display = 'block';
    document.getElementById('status').textContent = 'Ready';
});

socket.on('audio_error', (data) => {
    alert('Audio error: ' + data.error);
    document.getElementById('status').textContent = 'Ready';
});


socket.on('image_error', (data) => {
    alert('Image error: ' + data.error);
});

// Auto-scroll
setInterval(() => {
    const messagesDiv = document.getElementById('messages');
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}, 100);

