import cv2
import numpy as np


img = cv2.imread("images/example.jpeg")

img_bytes = cv2.imencode(".jpg", img)[1].tobytes()

print(img_bytes)

print(type(img_bytes))

img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)

cv2.imshow("Image", img)
cv2.waitKey(0)
cv2.destroyAllWindows()
