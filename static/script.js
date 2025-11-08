// Tab navigation
function showTab(tabId) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Remove active class from all buttons
    document.querySelectorAll('.nav-tab').forEach(button => {
        button.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById(tabId).classList.add('active');
    
    // Add active class to clicked button
    event.target.classList.add('active');
    
    // Initialize pagination for the active tab
    const tableType = tabId.replace('-tab', '');
    initPagination(tableType);
}

// Pagination state
const paginationState = {
    doctor: { currentPage: 1, pageSize: 20 },
    room: { currentPage: 1, pageSize: 20 },
    patient: { currentPage: 1, pageSize: 20 }
};

// Initialize pagination when page loads
document.addEventListener('DOMContentLoaded', function() {
    initPagination('doctor');
});

// Initialize pagination
function initPagination(tableType) {
    updateTableDisplay(tableType);
}

// Change page
function changePage(tableType, direction) {
    const state = paginationState[tableType];
    const totalRows = document.querySelectorAll(`.table-row[data-type="${tableType}"]`).length;
    const totalPages = Math.ceil(totalRows / state.pageSize);
    
    state.currentPage += direction;
    
    // Ensure page is within bounds
    if (state.currentPage < 1) state.currentPage = 1;
    if (state.currentPage > totalPages) state.currentPage = totalPages;
    
    updateTableDisplay(tableType);
}

// Update table display based on current page
function updateTableDisplay(tableType) {
    const state = paginationState[tableType];
    const rows = document.querySelectorAll(`.table-row[data-type="${tableType}"]`);
    const totalRows = rows.length;
    const totalPages = Math.ceil(totalRows / state.pageSize);
    
    // Calculate start and end indices
    const startIndex = (state.currentPage - 1) * state.pageSize;
    const endIndex = Math.min(startIndex + state.pageSize, totalRows);
    
    // Hide all rows
    rows.forEach(row => {
        row.style.display = 'none';
    });
    
    // Show only rows for current page
    for (let i = startIndex; i < endIndex; i++) {
        if (rows[i]) {
            rows[i].style.display = '';
        }
    }
    
    // Update page info
    const pageInfo = document.getElementById(`${tableType}-page-info`);
    if (pageInfo) {
        pageInfo.textContent = `Page ${state.currentPage} of ${totalPages}`;
    }
    
    // Update button states
    const prevBtn = document.querySelector(`#${tableType}-pagination .pagination-btn:first-child`);
    const nextBtn = document.querySelector(`#${tableType}-pagination .pagination-btn:last-child`);
    
    if (prevBtn) prevBtn.disabled = state.currentPage === 1;
    if (nextBtn) nextBtn.disabled = state.currentPage === totalPages;
}

// Add Font Awesome icons
const faLink = document.createElement('link');
faLink.rel = 'stylesheet';
faLink.href = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css';
document.head.appendChild(faLink);