const ws = new WebSocket("ws://10.104.18.28:80/ws");

const form = document.querySelector('form')

ws.onmessage = (event) => {
    const messages = document.getElementById('result')
    var message = document.createElement('img')
    console.log(URL.createObjectURL(event.data))
    message.src = URL.createObjectURL(event.data)
    messages.appendChild(message)
}

// Listen for form submit
form.addEventListener('submit', (e) => {
    console.log("Start processing...")
    e.preventDefault()

    const file = document.querySelector('[type=file]').files[0]
    console.log("File: " + file)
    ws.send(file)
})
