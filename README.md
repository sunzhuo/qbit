# qbit，Q#量子算法练习库

## 量子门电路、酉矩阵及示意图
|门名称|电路|酉矩阵|示意图|
|---|---|---|---|
|Pauli-X (X)|$-\boxed{X}-$|$$\begin{bmatrix} 0 & 1 \\ 1 & 0 \end{bmatrix}$$|![X门](./images/Xgate.gif)|
|Pauli-Y (Y)|$-\boxed{Y}-$|$$\begin{bmatrix} 0 & -i \\ i & 0 \end{bmatrix}$$|![Y门](./images/Ygate.gif)|
|Pauli-Z (Z)|$-\boxed{Z}-$|$$\begin{bmatrix} 1 & 0 \\ 0 & 1 \end{bmatrix}$$|![Z门](./images/Zgate.gif)|
|Hadamard (H)|$-\boxed{H}-$|$$ \frac{1}{\sqrt{2}}\begin{bmatrix} 1 & 1 \\ 1 & -1 \end{bmatrix} $$|![H门](./images/Hgate.gif)|
|Phase (S, P)|$-\boxed{S}- $|$$\begin{bmatrix} 1 & 0 \\ 0 & i \end{bmatrix}$$|![S门](./images/Sgate.gif)|
|$\pi/8$ (T)|$-\boxed{T}- $|$$\begin{bmatrix} 1 & 0 \\ 0 & i \end{bmatrix}$$|![S门](./images/Tgate.gif)|
|Controlled Not (CNOT, CX)|![CNOT门](./images/CNOTgate.png)|$$ \begin{bmatrix} I & 0 \\ 0 & X \end{bmatrix}$$|
|Controlled Z (CZ)|![CZ门](./images/CZgate.png)|$$ \begin{bmatrix} I & 0 \\ 0 & Z \end{bmatrix}$$||
|SWAP|![SWAP门](./images/SWAPgate.png)|$$\begin{bmatrix} 1 & 0 & 0 & 0 \\ 0 & 0 & 1 & 0 \\ 0 & 1 & 0 & 0 \\ 0 & 0 & 0 & 1 \end{bmatrix}$$||
|Toffoli (CCNOT, CCX, TOFF)|![TOFF门](./images/TOFFgate.png)|$$\begin{bmatrix} I & 0 & 0 & 0 \\ 0 & I & 0 & 0 \\ 0 & 0 & I & 0 \\ 0 & 0 & 0 & X \end{bmatrix}$$||
|Measure|![Measure门](./images/Measure.png)||![Measure门](./images/Measure.gif)|

## 创建贝尔纠缠态
首先准备两个量子比特$|0\rangle, |0\rangle$，然后对第一个量子比特执行H门，再对两个量子比特执行CNOT门，最后得到$\frac{1}{\sqrt{2}}(|00\rangle + |11\rangle)$。矩阵表示为：

1. 准备两个量子比特$\begin{bmatrix} 1 \\ 0 \end{bmatrix}$，$\begin{bmatrix} 1 \\ 0 \end{bmatrix}$

2. 对第一个量子比特执行H门：$$ \frac{1}{\sqrt{2}}\begin{bmatrix} 1 & 1 \\ 1 & -1 \end{bmatrix} \begin{bmatrix} 1 \\ 0 \end{bmatrix}=\frac{1}{\sqrt{2}}\begin{bmatrix} 1 \\ 1 \end{bmatrix} $$

3. 对两个量子比特执行CNOT门：$$\begin{bmatrix} I & 0 \\ 0 & X \end{bmatrix} \left(\frac{1}{\sqrt{2}}\begin{bmatrix} 1 \\ 1 \end{bmatrix} \otimes \begin{bmatrix} 1 \\ 0 \end{bmatrix}\right) = \frac{1}{\sqrt{2}}\begin{bmatrix} 1 \\ 0 \\ 0 \\ 1 \end{bmatrix}$$