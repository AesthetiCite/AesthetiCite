const axios = require('axios');

async function getRandomJoke() {
  try {
    const response = await axios.get('https://official-joke-api.appspot.com/random_joke');
    const joke = response.data;
    console.log(`${joke.setup}\n${joke.punchline}`);
  } catch (error) {
    console.error("Failed to fetch a joke:", error.message);
  }
}

getRandomJoke();