function fetchVideoInfo() {
  const videoUrl = document.getElementById("videoUrl").value;
  const thumbnail = document.getElementById("thumbnail");
  const videoTitle = document.getElementById("videoTitle");
  const resolutionList = document.getElementById("resolutionList");
  const loadingMessage = document.getElementById("loading");
  const audioDownloadSection = document.getElementById("audioDownload");

  if (!videoUrl) {
    alert("Please enter a valid video URL.");
    return;
  }

  // Show loading message
  loadingMessage.style.display = "flex";

  fetch("/api/video_info", {
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
      audioDownloadSection.style.display = "block";
    })
    .catch((error) => {
      console.error(error);
      loadingMessage.style.display = "none";

      // Better error messages based on error type
      let errorMessage = "Error fetching video info. Please try again.";

      if (error.message && error.message.includes("name resolution")) {
        errorMessage =
          "Network connection issue. Please check your internet connection and try again.";
      } else if (error.message && error.message.includes("404")) {
        errorMessage = "Video not found. Please check the URL and try again.";
      } else if (error.message && error.message.includes("403")) {
        errorMessage =
          "Video is private or restricted. Please try a different video.";
      } else if (error.message && error.message.includes("rate")) {
        errorMessage = "Too many requests. Please wait a moment and try again.";
      }

      alert(errorMessage);
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

  progressWrapper.style.display = "block";
  progressText.textContent = "Starting download...";

  // Start fast progress updates immediately
  startProgressUpdate();

  fetch(
    `/download?url=${encodeURIComponent(videoUrl)}&resolution=${resolution}&title=${encodeURIComponent(title)}`,
    {
      method: "GET",
      headers: {
        Accept: "application/octet-stream",
      },
    },
  )
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return response.blob();
    })
    .then((blob) => {
      // Download completed successfully
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.style.display = "none";
      a.href = url;
      a.download = `${title}_${resolution}p.mp4`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      progressWrapper.style.display = "none";
    })
    .catch((error) => {
      console.error("Download error:", error);
      progressWrapper.style.display = "none";

      // Better error messages for download failures
      let errorMessage = "Download failed. Please try again.";

      if (error.message && error.message.includes("name resolution")) {
        errorMessage =
          "Network connection lost during download. Please check your connection and try again.";
      } else if (error.message && error.message.includes("404")) {
        errorMessage =
          "Video no longer available. Please try a different video.";
      } else if (error.message && error.message.includes("403")) {
        errorMessage =
          "Access denied. This video may be private or geo-blocked.";
      } else if (error.message && error.message.includes("timeout")) {
        errorMessage =
          "Download timed out. Please try again with a smaller video or check your connection.";
      }

      alert(errorMessage);
    });
}

function downloadAudio(title, format) {
  const videoUrl = document.getElementById("videoUrl").value;
  const progressWrapper = document.getElementById("progressWrapper");
  const progressBar = document.getElementById("progress");
  const progressText = document.getElementById("progressText");

  progressWrapper.style.display = "block";
  progressText.textContent = "Starting download...";

  // Start fast progress updates immediately
  startProgressUpdate();

  fetch(
    `/download_audio?url=${encodeURIComponent(videoUrl)}&title=${encodeURIComponent(title)}&format=${format}`,
    {
      method: "GET",
      headers: {
        Accept: "application/octet-stream",
      },
    },
  )
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return response.blob();
    })
    .then((blob) => {
      // Download completed successfully
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.style.display = "none";
      a.href = url;
      a.download = `${title}.${format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      progressWrapper.style.display = "none";
    })
    .catch((error) => {
      console.error("Download error:", error);
      progressWrapper.style.display = "none";

      // Better error messages for audio download failures
      let errorMessage = "Audio download failed. Please try again.";

      if (error.message && error.message.includes("name resolution")) {
        errorMessage =
          "Network connection lost during download. Please check your connection and try again.";
      } else if (error.message && error.message.includes("404")) {
        errorMessage = "Audio not available. Please try a different video.";
      } else if (error.message && error.message.includes("403")) {
        errorMessage =
          "Access denied. This video may be private or geo-blocked.";
      } else if (error.message && error.message.includes("ffmpeg")) {
        errorMessage =
          "Audio conversion failed. Please try the WEBM format instead.";
      }

      alert(errorMessage);
    });
}

function startProgressUpdate() {
  const progressBar = document.getElementById("progress");
  const progressText = document.getElementById("progressText");

  const interval = setInterval(() => {
    fetch("/progress")
      .then((response) => response.json())
      .then((data) => {
        const progress = data.progress || 0;
        progressBar.style.width = `${progress}%`;
        progressText.textContent = `Downloading... ${Math.round(progress)}%`;

        // Stop polling when complete
        if (progress >= 100) {
          clearInterval(interval);
          progressText.textContent = "Download complete!";
        }
      })
      .catch((error) => {
        console.error("Error fetching progress:", error);
        // Don't stop the interval on network errors, keep trying
        if (error.message && error.message.includes("name resolution")) {
          progressText.textContent = "Connection issue - retrying...";
        }
      });
  }, 500); // Fast updates every 500ms

  // Cleanup interval after 10 minutes max
  setTimeout(() => {
    clearInterval(interval);
  }, 600000);
}

function checkEnter(event) {
  if (event.key === "Enter") {
    fetchVideoInfo();
  }
}
