// 进度环动画
document.addEventListener('DOMContentLoaded', function() {
    const circles = document.querySelectorAll('.progress-ring-circle');
    circles.forEach(circle => {
        const radius = circle.r.baseVal.value;
        const circumference = radius * 2 * Math.PI;
        
        circle.style.strokeDasharray = `${circumference} ${circumference}`;
        circle.style.strokeDashoffset = circumference;
        
        const value = parseInt(circle.parentElement.parentElement.dataset.value);
        const offset = circumference - (value / 100) * circumference;
        circle.style.strokeDashoffset = offset;
    });
}); 