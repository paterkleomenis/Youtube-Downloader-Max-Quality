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
  progressText.textContent = "Starting download...";

  // Request download preparation (server processes in background)
  fetch("/prepare_download", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ 
      url: videoUrl, 
      resolution: resolution, 
      title: title,
      type: "video"
    }),
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.error) {
        alert(data.error);
        progressWrapper.style.display = "none";
        return;
      }
      
      // Start polling for download completion
      pollDownloadStatus(data.download_id, title, resolution, "video");
    })
    .catch((error) => {
      console.error(error);
      alert("Error starting download. Please try again.");
      progressWrapper.style.display = "none";
    });
}

function downloadAudio(title, format) {
  const videoUrl = document.getElementById("videoUrl").value;
  const progressWrapper = document.getElementById("progressWrapper");
  const progressBar = document.getElementById("progress");
  const progressText = document.getElementById("progressText");
  progressWrapper.style.display = "block"; // Show progress bar
  progressText.textContent = "Starting download...";

  // Request download preparation (server processes in background)
  fetch("/prepare_download", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ 
      url: videoUrl, 
      title: title,
      format: format,
      type: "audio"
    }),
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.error) {
        alert(data.error);
        progressWrapper.style.display = "none";
        return;
      }
      
      // Start polling for download completion
      pollDownloadStatus(data.download_id, title, null, "audio", format);
    })
    .catch((error) => {
      console.error(error);
      alert("Error starting download. Please try again.");
      progressWrapper.style.display = "none";
    });
}

function pollDownloadStatus(downloadId, title, resolution, type, format) {
  const progressBar = document.getElementById("progress");
  const progressText = document.getElementById("progressText");
  const progressWrapper = document.getElementById("progressWrapper");

  const interval = setInterval(() => {
    fetch(`/download_status/${downloadId}`)
      .then((response) => response.json())
      .then((data) => {
        console.log(data);
        const progress = data.progress;
        progressBar.style.width = `${progress}%`;
        
        if (data.status === "processing") {
          progressText.textContent = `Processing... ${progress | 0}%`;
        } else if (data.status === "ready") {
          progressText.textContent = "Download ready! Starting...";
          clearInterval(interval);
          
          // Download the prepared file directly
          const link = document.createElement("a");
          link.href = `/get_download/${downloadId}`;
          
          if (type === "video") {
            link.download = `${title}_${resolution}p.mp4`;
          } else {
            link.download = `${title}.${format}`;
          }
          
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          progressWrapper.style.display = "none";
        } else if (data.status === "error") {
          clearInterval(interval);
          alert("Error processing download: " + (data.error || "Unknown error"));
          progressWrapper.style.display = "none";
        }
      })
      .catch((error) => {
        console.error("Error checking download status:", error);
        clearInterval(interval);
        alert("Error checking download status. Please try again.");
        progressWrapper.style.display = "none";
      });
  }, 2000); // Poll every 2 seconds
}

function startProgressUpdate() {
  // This function is now deprecated - keeping for backward compatibility
  // New downloads use pollDownloadStatus instead
}

function checkEnter(event) {
  if (event.key === "Enter") {
    fetchVideoInfo();
  }
}

