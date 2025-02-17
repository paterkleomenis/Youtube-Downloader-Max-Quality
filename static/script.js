function fetchVideoInfo() {
  const videoUrl = document.getElementById("videoUrl").value;
  const thumbnail = document.getElementById("thumbnail");
  const videoTitle = document.getElementById("videoTitle");
  const resolutionList = document.getElementById("resolutionList");
  const loadingMessage = document.getElementById("loading"); // Select loading message
  const audioDownloadSection = document.getElementById("audioDownload"); // Select audio download section

  if (!videoUrl) {
    alert("Please enter a valid video URL.");
    return;
  }

  // Show loading message
  loadingMessage.style.display = "flex";

  fetch("/video_info", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ url: videoUrl }),
  })
    .then((response) => response.json())
    .then((data) => {
      // Hide loading message
      loadingMessage.style.display = "none";

      if (data.error) {
        alert(data.error);
        return;
      }

      // Display video info
      videoTitle.textContent = data.title;
      thumbnail.src = data.thumbnail;
      thumbnail.style.display = "block";

      // Display available resolutions
      resolutionList.innerHTML = "";
      data.resolutions.forEach((res) => {
        if (res !== 180) {
          const li = document.createElement("li");
          li.textContent = `${res}p`;
          const downloadButton = document.createElement("button");
          downloadButton.textContent = "Download";
          downloadButton.onclick = () => downloadVideo(res, data.title);
          li.appendChild(downloadButton);
          resolutionList.appendChild(li);
        }
      });

      // Show the audio download section after fetching video info
      audioDownloadSection.style.display = "block"; // Make the audio download section visible
    })
    .catch((error) => {
      console.error(error);
      alert("Error fetching video info. Please try again.");
    });
}

function downloadAudioFormat(format) {
  const videoTitle = document.getElementById("videoTitle").textContent;
  downloadAudio(videoTitle, format);
}

function downloadVideo(resolution, title) {
  const videoUrl = document.getElementById("videoUrl").value;
  const progressWrapper = document.getElementById("progressWrapper");
  const progressBar = document.getElementById("progress");
  const progressText = document.getElementById("progressText");
  progressWrapper.style.display = "block"; // Show progress bar

  fetch(
    `/download?url=${encodeURIComponent(videoUrl)}&resolution=${resolution}&title=${encodeURIComponent(title)}`,
  )
    .then((response) => {
      if (!response.ok) throw new Error("Network response was not ok.");

      const reader = response.body.getReader();
      const contentLength = +response.headers.get("Content-Length");
      let receivedLength = 0;
      let chunks = [];

      return new Promise((resolve, reject) => {
        reader
          .read()
          .then(function processText({ done, value }) {
            if (done) {
              resolve(new Blob(chunks));
              return;
            }
            chunks.push(value);
            receivedLength += value.length;
            progressBar.style.width = `${(receivedLength / contentLength) * 100}%`;
            progressText.textContent = `Downloading... ${((receivedLength / contentLength) * 100) | 0}%`;
            reader.read().then(processText).catch(reject);
          })
          .catch(reject);
      });
    })
    .then((blob) => {
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${title}_${resolution}p.mp4`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      progressWrapper.style.display = "none"; // Hide progress bar
    })
    .catch((error) => {
      console.error(error);
      alert("Error downloading video. Please try again.");
      progressWrapper.style.display = "none"; // Hide progress bar
    });

  // Start progress bar update with backend hook
  startProgressUpdate();
}

function downloadAudio(title, format) {
  const videoUrl = document.getElementById("videoUrl").value;
  const progressWrapper = document.getElementById("progressWrapper");
  const progressBar = document.getElementById("progress");
  const progressText = document.getElementById("progressText");
  progressWrapper.style.display = "block"; // Show progress bar

  fetch(
    `/download_audio?url=${encodeURIComponent(videoUrl)}&title=${encodeURIComponent(title)}&format=${format}`,
  )
    .then((response) => {
      console.log(response);
      if (!response.ok) throw new Error("Network response was not ok.");

      const reader = response.body.getReader();
      const contentLength = +response.headers.get("Content-Length");
      let receivedLength = 0;
      let chunks = [];

      return new Promise((resolve, reject) => {
        reader
          .read()
          .then(function processText({ done, value }) {
            if (done) {
              resolve(new Blob(chunks));
              return;
            }
            chunks.push(value);
            receivedLength += value.length;
            progressBar.style.width = `${(receivedLength / contentLength) * 100}%`;
            progressText.textContent = `Downloading... ${((receivedLength / contentLength) * 100) | 0}%`;
            reader.read().then(processText).catch(reject);
          })
          .catch(reject);
      });
    })
    .then((blob) => {
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${title}.${format}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      progressWrapper.style.display = "none"; // Hide progress bar
    })
    .catch((error) => {
      console.error(error);
      alert("Error downloading audio. Please try again.");
      progressWrapper.style.display = "none"; // Hide progress bar
    });

  // Start progress bar update with backend hook
  startProgressUpdate();
}

function startProgressUpdate() {
  const progressBar = document.getElementById("progress");
  const progressText = document.getElementById("progressText");

  // Poll the server every second for progress updates
  const interval = setInterval(() => {
    fetch("/progress")
      .then((response) => response.json())
      .then((data) => {
        console.log(data);
        const progress = data.progress;
        progressBar.style.width = `${progress}%`;
        progressText.textContent = `Downloading... ${progress | 0}%`;
        if (progress >= 100) {
          clearInterval(interval); // Stop the polling once the download is complete
        }
      })
      .catch((error) => {
        console.error("Error updating progress:", error);
        clearInterval(interval); // Stop polling on error
      });
  }, 1000); // Poll every second
}

function checkEnter(event) {
  if (event.key === "Enter") {
    fetchVideoInfo();
  }
}

