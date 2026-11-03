// 공개 설정 (비밀 아님). VAPID 공개키는 브라우저가 푸시 구독할 때 쓰는 공개값입니다.
window.HUB_CONFIG = {
  dataBase: location.hostname === "localhost" || location.hostname === "127.0.0.1"
    ? "../data-local/"
    : "https://raw.githubusercontent.com/hkseong/rescene-hub/data/data/",
  workerUrl: "https://rescene-hub.rescene-hub.workers.dev",
  vapidPublicKey: "BPSwJTxWI0uvvZeX-7X_hlEenF4L3GBVJuW7rMt1oThY0kL2re0_up6qEDQRk7LOccvL0wMbUrY9coaHwQzrCEk",
  debut: "2024-03-26",
};
