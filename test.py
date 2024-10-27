import cv2
import numpy as np
import json
import base64
from io import BytesIO
from PIL import Image

img = cv2.imread("images/example.jpeg")

img_bytes = cv2.imencode(".jpg", img)[1].tobytes()

data = json.dumps({"bytes": base64.b64encode(img_bytes).decode("utf-8")})

data = json.loads(data)
img = base64.b64decode(data["bytes"].encode("utf-8"))
image = Image.open(BytesIO(img))
image = np.array(image)
cv2.imshow("Image", image)
cv2.waitKey(0)
cv2.destroyAllWindows()
